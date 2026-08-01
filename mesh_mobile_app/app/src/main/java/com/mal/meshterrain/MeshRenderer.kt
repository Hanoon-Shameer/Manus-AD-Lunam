package com.mal.meshterrain

import android.opengl.GLES20
import android.opengl.Matrix

class MeshRenderer {

    private var program = 0
    private var positionAttrib = 0
    private var mvpMatrixUniform = 0

    private val vertexShaderCode = """
        uniform mat4 u_MVPMatrix;
        attribute vec4 a_Position;
        varying vec3 v_WorldPos;
        varying float v_Dist;

        void main() {
            gl_Position = u_MVPMatrix * a_Position;
            v_WorldPos = a_Position.xyz;
            v_Dist = gl_Position.w; // Distance from camera
        }
    """.trimIndent()

    private val fragmentShaderCode = """
        precision mediump float;
        varying vec3 v_WorldPos;
        varying float v_Dist;

        void main() {
            // 5cm world grid - Stable Topographical Spacing
            vec3 spacing = vec3(0.06, 0.05, 0.06); 
            
            // Reversed Thickness: Bolder at a distance (v_Dist)
            float thickness = 0.0015 + clamp(v_Dist * 0.002, 0.0, 0.008);
            
            vec3 grid = abs(fract(v_WorldPos / spacing - 0.5) - 0.5) * spacing;
            
            float lineX = smoothstep(thickness, thickness * 0.5, grid.x);
            float lineY = smoothstep(thickness, thickness * 0.5, grid.y);
            float lineZ = smoothstep(thickness, thickness * 0.5, grid.z);
            
            // Combine to form a topographical 3D skin
            float line = max(max(lineX, lineY), lineZ);
            
            // Tech-Cyan Aesthetic
            vec3 color = vec3(0.4, 0.9, 1.0);
            
            // Simple lighting based on world-Y height for depth perception
            float lighting = 0.7 + 0.3 * sin(v_WorldPos.y * 5.0);
            
            // Semi-transparent face + Bright grid lines
            float faceAlpha = 0.1; 
            float lineAlpha = line * 0.85;
            
            gl_FragColor = vec4(color * lighting, max(faceAlpha, lineAlpha));
        }
    """.trimIndent()

    fun createOnGlThread() {
        val vertexShader = loadShader(GLES20.GL_VERTEX_SHADER, vertexShaderCode)
        val fragmentShader = loadShader(GLES20.GL_FRAGMENT_SHADER, fragmentShaderCode)

        program = GLES20.glCreateProgram().also {
            GLES20.glAttachShader(it, vertexShader)
            GLES20.glAttachShader(it, fragmentShader)
            GLES20.glLinkProgram(it)
        }

        positionAttrib = GLES20.glGetAttribLocation(program, "a_Position")
        mvpMatrixUniform = GLES20.glGetUniformLocation(program, "u_MVPMatrix")
    }

    fun draw(mesh: TerrainMesh, viewMatrix: FloatArray, projectionMatrix: FloatArray) {
        GLES20.glUseProgram(program)
        GLES20.glEnable(GLES20.GL_BLEND)
        GLES20.glBlendFunc(GLES20.GL_SRC_ALPHA, GLES20.GL_ONE_MINUS_SRC_ALPHA)

        val mvpMatrix = FloatArray(16)
        Matrix.multiplyMM(mvpMatrix, 0, projectionMatrix, 0, viewMatrix, 0)
        GLES20.glUniformMatrix4fv(mvpMatrixUniform, 1, false, mvpMatrix, 0)

        mesh.vertexBuffer.position(0)
        GLES20.glVertexAttribPointer(positionAttrib, 3, GLES20.GL_FLOAT, false, 0, mesh.vertexBuffer)
        GLES20.glEnableVertexAttribArray(positionAttrib)

        mesh.indexBuffer.position(0)
        GLES20.glDrawElements(
            GLES20.GL_TRIANGLES,
            mesh.indexCount,
            GLES20.GL_UNSIGNED_SHORT,
            mesh.indexBuffer
        )

        GLES20.glDisableVertexAttribArray(positionAttrib)
        GLES20.glDisable(GLES20.GL_BLEND)
    }

    private fun loadShader(type: Int, code: String): Int {
        val shader = GLES20.glCreateShader(type)
        GLES20.glShaderSource(shader, code)
        GLES20.glCompileShader(shader)
        return shader
    }
}
