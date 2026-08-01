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
    private val terrainMesh = TerrainMesh(80, 50)

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
    private val flipMatrix = android.graphics.Matrix()
    
    // Scale for streaming to improve FPS (e.g., 0.5 = half resolution)
    private val STREAM_SCALE = 0.5f 

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
        
        // Swapped width/height for PC Landscape orientation
        val targetWidth = (height * STREAM_SCALE).toInt()
        val targetHeight = (width * STREAM_SCALE).toInt()
        
        // Re-allocate capture buffers on resize
        pixelBuffer = ByteBuffer.allocateDirect(width * height * 4).order(ByteOrder.LITTLE_ENDIAN)
        captureBitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        
        // This bitmap will be sent to the PC in landscape
        flippedBitmap = Bitmap.createBitmap(targetWidth, targetHeight, Bitmap.Config.ARGB_8888)
        captureCanvas = android.graphics.Canvas(flippedBitmap!!)
        
        flipMatrix.reset()
        // 1. Scale down
        flipMatrix.postScale(STREAM_SCALE, STREAM_SCALE)
        // 2. Rotate 90 degrees right for landscape
        flipMatrix.postRotate(90f)
        // 3. Translate to fit the rotated dimensions
        flipMatrix.postTranslate(targetWidth.toFloat(), 0f)
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

        // Capture more frequently for higher FPS
        if (streamingListener != null) {
            captureFrame(streamingListener!!)
        }
    }

    private fun captureFrame(listener: (Bitmap) -> Unit) {
        // If the worker thread is still busy with the previous frame, drop this one
        if (isCompressing) return

        val buffer = pixelBuffer ?: return
        val bitmap = captureBitmap ?: return
        val flipped = flippedBitmap ?: return
        val canvas = captureCanvas ?: return
        
        buffer.rewind()
        GLES20.glReadPixels(0, 0, viewportWidth, viewportHeight, GLES20.GL_RGBA, GLES20.GL_UNSIGNED_BYTE, buffer)
        
        buffer.rewind()
        bitmap.copyPixelsFromBuffer(buffer)
        
        // Scale and flip in one go on the GPU-backed canvas
        canvas.drawBitmap(bitmap, flipMatrix, null)
        
        // Copy the small scaled bitmap for the stream
        val bitmapCopy = flipped.copy(flipped.config ?: Bitmap.Config.ARGB_8888, false)
        
        isCompressing = true
        compressionExecutor.execute {
            try {
                listener(bitmapCopy)
            } catch (e: Exception) {
            } finally {
                isCompressing = false
            }
        }
    }
}
