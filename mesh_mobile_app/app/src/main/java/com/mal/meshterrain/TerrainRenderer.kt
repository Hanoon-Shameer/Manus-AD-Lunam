package com.mal.meshterrain

import android.graphics.Bitmap
import android.opengl.GLES11Ext
import android.opengl.GLES20
import android.opengl.GLSurfaceView
import com.google.ar.core.Session
import java.nio.ByteBuffer
import java.nio.ByteOrder
import javax.microedition.khronos.egl.EGLConfig
import javax.microedition.khronos.opengles.GL10

class TerrainRenderer(private val session: Session) : GLSurfaceView.Renderer {

    private var cameraTextureId: Int = -1
    private val backgroundRenderer = BackgroundRenderer()
    private val meshRenderer = MeshRenderer()
    private val terrainMesh = TerrainMesh(80, 45)

    private var viewportWidth = 0
    private var viewportHeight = 0
    private var streamingListener: ((Bitmap) -> Unit)? = null
    
    private val compressionExecutor = java.util.concurrent.Executors.newSingleThreadExecutor()
    private var isCompressing = false

    // Buffers for frame capture to avoid allocations
    private var pixelBuffer: ByteBuffer? = null
    private var captureBitmap: Bitmap? = null
    private var flippedBitmap: Bitmap? = null
    private var captureCanvas: android.graphics.Canvas? = null
    private val flipMatrix = android.graphics.Matrix().apply { postScale(1f, -1f); postTranslate(0f, 0f) }
    
    private var frameCounter = 0

    fun setStreamingListener(listener: ((Bitmap) -> Unit)?) {
        streamingListener = listener
    }

    override fun onSurfaceCreated(gl: GL10?, config: EGLConfig?) {
        GLES20.glClearColor(0f, 0f, 0f, 1f)

        val textures = IntArray(1)
        GLES20.glGenTextures(1, textures, 0)
        cameraTextureId = textures[0]

        val target = GLES11Ext.GL_TEXTURE_EXTERNAL_OES
        GLES20.glBindTexture(target, cameraTextureId)
        GLES20.glTexParameteri(target, GLES20.GL_TEXTURE_MIN_FILTER, GLES20.GL_LINEAR)
        GLES20.glTexParameteri(target, GLES20.GL_TEXTURE_MAG_FILTER, GLES20.GL_LINEAR)
        GLES20.glTexParameteri(target, GLES20.GL_TEXTURE_WRAP_S, GLES20.GL_CLAMP_TO_EDGE)
        GLES20.glTexParameteri(target, GLES20.GL_TEXTURE_WRAP_T, GLES20.GL_CLAMP_TO_EDGE)

        session.setCameraTextureName(cameraTextureId)
        backgroundRenderer.createOnGlThread()
        meshRenderer.createOnGlThread()
        
        GLES20.glEnable(GLES20.GL_DEPTH_TEST)
        GLES20.glDepthMask(true)
    }

    override fun onSurfaceChanged(gl: GL10?, width: Int, height: Int) {
        GLES20.glViewport(0, 0, width, height)
        session.setDisplayGeometry(0, width, height)
        viewportWidth = width
        viewportHeight = height
        
        // Re-allocate capture buffers on resize
        pixelBuffer = ByteBuffer.allocateDirect(width * height * 4).order(ByteOrder.LITTLE_ENDIAN)
        captureBitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        flippedBitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        captureCanvas = android.graphics.Canvas(flippedBitmap!!)
        
        flipMatrix.reset()
        flipMatrix.postScale(1f, -1f)
        flipMatrix.postTranslate(0f, height.toFloat())
    }

    override fun onDrawFrame(gl: GL10?) {
        GLES20.glClear(GLES20.GL_COLOR_BUFFER_BIT or GLES20.GL_DEPTH_BUFFER_BIT)

        val frame = try { session.update() } catch(e: Exception) { return }
        val camera = frame.camera
        backgroundRenderer.draw(cameraTextureId, frame)

        terrainMesh.updateHeights(frame)

        val viewMatrix = FloatArray(16)
        val projectionMatrix = FloatArray(16)
        camera.getViewMatrix(viewMatrix, 0)
        camera.getProjectionMatrix(projectionMatrix, 0, 0.1f, 100f)

        meshRenderer.draw(terrainMesh, viewMatrix, projectionMatrix)

        // Capture every 3rd frame to reduce overhead while streaming
        if (streamingListener != null && ++frameCounter % 3 == 0) {
            captureFrame(streamingListener!!)
        }
    }

    private fun captureFrame(listener: (Bitmap) -> Unit) {
        if (isCompressing) return

        val buffer = pixelBuffer ?: return
        val bitmap = captureBitmap ?: return
        val flipped = flippedBitmap ?: return
        val canvas = captureCanvas ?: return
        
        buffer.rewind()
        GLES20.glReadPixels(0, 0, viewportWidth, viewportHeight, GLES20.GL_RGBA, GLES20.GL_UNSIGNED_BYTE, buffer)
        
        buffer.rewind()
        bitmap.copyPixelsFromBuffer(buffer)
        
        canvas.drawBitmap(bitmap, flipMatrix, null)
        
        // Create a copy to send to the server to avoid race conditions with next glReadPixels
        val bitmapCopy = flipped.copy(flipped.config ?: Bitmap.Config.ARGB_8888, false)
        
        isCompressing = true
        compressionExecutor.execute {
            try {
                listener(bitmapCopy)
            } finally {
                isCompressing = false
            }
        }
    }
}
