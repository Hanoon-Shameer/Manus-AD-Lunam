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
            // Sharper 4cm world grid for more detailed warping
            vec3 spacing = vec3(0.04, 0.04, 0.04); 
            
            // Scaled thickness: Thinner up close, Bold at a distance
            float thickness = 0.0012 + clamp(v_Dist * 0.003, 0.0, 0.012);
            
            vec3 grid = abs(fract(v_WorldPos / spacing - 0.5) - 0.5) * spacing;
            
            float lineX = smoothstep(thickness, thickness * 0.4, grid.x);
            float lineY = smoothstep(thickness, thickness * 0.4, grid.y);
            float lineZ = smoothstep(thickness, thickness * 0.4, grid.z);
            
            float line = max(max(lineX, lineY), lineZ);
            
            // Tech-Cyan with a bit more vibrancy
            vec3 color = vec3(0.3, 1.0, 0.9);
            
            // Emphasize the "Humps" with height-based shading
            float heightFactor = fract(v_WorldPos.y * 10.0); // 10cm bands
            float heightGlow = smoothstep(0.9, 1.0, heightFactor) * 0.4;
            
            // Lighting based on depth to show object curvature better
            float lighting = 0.6 + 0.4 * abs(sin(v_WorldPos.y * 8.0));
            
            float faceAlpha = 0.12; 
            float lineAlpha = line * 0.9 + heightGlow;
            
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
