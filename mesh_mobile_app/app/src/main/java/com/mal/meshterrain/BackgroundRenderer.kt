package com.mal.meshterrain

import android.opengl.GLES11Ext
import android.opengl.GLES20
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer

class BackgroundRenderer {

    private var quadProgram = 0
    private var quadPositionAttrib = 0
    private var quadTexCoordAttrib = 0
    private var textureUniform = 0

    private lateinit var quadVertices: FloatBuffer
    private lateinit var quadTexCoords: FloatBuffer
    private lateinit var quadTexCoordsTransformed: FloatBuffer
    private var quadTexCoordsInitialized = false

    private val vertexShaderCode = """
        attribute vec4 a_Position;
        attribute vec2 a_TexCoord;
        varying vec2 v_TexCoord;
        void main() {
            gl_Position = a_Position;
            v_TexCoord = a_TexCoord;
        }
    """.trimIndent()

    private val fragmentShaderCode = """
        #extension GL_OES_EGL_image_external : require
        precision mediump float;
        varying vec2 v_TexCoord;
        uniform samplerExternalOES u_Texture;
        void main() {
            gl_FragColor = texture2D(u_Texture, v_TexCoord);
        }
    """.trimIndent()

    fun createOnGlThread() {
        // Full-screen quad, positions in clip space (-1 to 1)
        val vertices = floatArrayOf(
            -1f, -1f,
            1f, -1f,
            -1f,  1f,
            1f,  1f
        )
        val texCoords = floatArrayOf(
            0f, 1f,
            1f, 1f,
            0f, 0f,
            1f, 0f
        )

        quadVertices = ByteBuffer.allocateDirect(vertices.size * 4)
            .order(ByteOrder.nativeOrder()).asFloatBuffer().apply {
                put(vertices); position(0)
            }
        quadTexCoords = ByteBuffer.allocateDirect(texCoords.size * 4)
            .order(ByteOrder.nativeOrder()).asFloatBuffer().apply {
                put(texCoords); position(0)
            }
        quadTexCoordsTransformed = ByteBuffer.allocateDirect(texCoords.size * 4)
            .order(ByteOrder.nativeOrder()).asFloatBuffer()

        val vertexShader = loadShader(GLES20.GL_VERTEX_SHADER, vertexShaderCode)
        val fragmentShader = loadShader(GLES20.GL_FRAGMENT_SHADER, fragmentShaderCode)

        quadProgram = GLES20.glCreateProgram().also {
            GLES20.glAttachShader(it, vertexShader)
            GLES20.glAttachShader(it, fragmentShader)
            GLES20.glLinkProgram(it)
        }

        quadPositionAttrib = GLES20.glGetAttribLocation(quadProgram, "a_Position")
        quadTexCoordAttrib = GLES20.glGetAttribLocation(quadProgram, "a_TexCoord")
        textureUniform = GLES20.glGetUniformLocation(quadProgram, "u_Texture")
    }

    fun draw(cameraTextureId: Int, frame: com.google.ar.core.Frame) {
        // ARCore may need to transform UVs each frame (rotation/crop) if geometry changed
        if (frame.hasDisplayGeometryChanged() || !quadTexCoordsInitialized) {
            frame.transformCoordinates2d(
                com.google.ar.core.Coordinates2d.OPENGL_NORMALIZED_DEVICE_COORDINATES,
                quadVertices,
                com.google.ar.core.Coordinates2d.TEXTURE_NORMALIZED,
                quadTexCoordsTransformed
            )
            quadTexCoordsInitialized = true
        }

        GLES20.glDisable(GLES20.GL_DEPTH_TEST)
        GLES20.glDepthMask(false)

        GLES20.glUseProgram(quadProgram)
        GLES20.glActiveTexture(GLES20.GL_TEXTURE0)
        GLES20.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, cameraTextureId)
        GLES20.glUniform1i(textureUniform, 0)

        quadVertices.position(0)
        GLES20.glVertexAttribPointer(quadPositionAttrib, 2, GLES20.GL_FLOAT, false, 0, quadVertices)
        GLES20.glEnableVertexAttribArray(quadPositionAttrib)

        quadTexCoordsTransformed.position(0)
        GLES20.glVertexAttribPointer(quadTexCoordAttrib, 2, GLES20.GL_FLOAT, false, 0, quadTexCoordsTransformed)
        GLES20.glEnableVertexAttribArray(quadTexCoordAttrib)

        GLES20.glDrawArrays(GLES20.GL_TRIANGLE_STRIP, 0, 4)

        GLES20.glDisableVertexAttribArray(quadPositionAttrib)
        GLES20.glDisableVertexAttribArray(quadTexCoordAttrib)
        GLES20.glDepthMask(true)
        GLES20.glEnable(GLES20.GL_DEPTH_TEST)
    }

    private fun loadShader(type: Int, code: String): Int {
        return GLES20.glCreateShader(type).also {
            GLES20.glShaderSource(it, code)
            GLES20.glCompileShader(it)
        }
    }
}
