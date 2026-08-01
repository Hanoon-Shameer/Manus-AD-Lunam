package com.mal.meshterrain

import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer
import java.nio.ShortBuffer

class TerrainMesh(private val gridWidth: Int, private val gridHeight: Int) {

    val vertexCount = gridWidth * gridHeight
    lateinit var vertexBuffer: FloatBuffer
    lateinit var indexBuffer: ShortBuffer
    var indexCount = 0

    private val displayUvBuffer: FloatBuffer = ByteBuffer.allocateDirect(vertexCount * 2 * 4)
        .order(ByteOrder.nativeOrder()).asFloatBuffer()
    private val depthUvBuffer: FloatBuffer = ByteBuffer.allocateDirect(vertexCount * 2 * 4)
        .order(ByteOrder.nativeOrder()).asFloatBuffer()

    private val smoothMeters = FloatArray(vertexCount)
    private val depthLerp = 0.7f // Stiff but clean

    init {
        buildGrid()
        buildIndices()
    }

    private fun buildGrid() {
        vertexBuffer = ByteBuffer.allocateDirect(vertexCount * 3 * 4)
            .order(ByteOrder.nativeOrder()).asFloatBuffer()
        
        displayUvBuffer.position(0)
        for (row in 0 until gridHeight) {
            val v = row.toFloat() / (gridHeight - 1)
            for (col in 0 until gridWidth) {
                val u = col.toFloat() / (gridWidth - 1)
                displayUvBuffer.put(u); displayUvBuffer.put(v)
            }
        }
        displayUvBuffer.position(0)
    }

    private fun buildIndices() {
        val indices = ShortArray((gridHeight - 1) * (gridWidth - 1) * 6)
        var i = 0
        for (row in 0 until gridHeight - 1) {
            for (col in 0 until gridWidth - 1) {
                val topLeft = (row * gridWidth + col).toShort()
                val topRight = (row * gridWidth + col + 1).toShort()
                val bottomLeft = ((row + 1) * gridWidth + col).toShort()
                val bottomRight = ((row + 1) * gridWidth + col + 1).toShort()

                indices[i++] = topLeft; indices[i++] = bottomLeft; indices[i++] = topRight
                indices[i++] = topRight; indices[i++] = bottomLeft; indices[i++] = bottomRight
            }
        }
        indexCount = indices.size
        indexBuffer = ByteBuffer.allocateDirect(indices.size * 2)
            .order(ByteOrder.nativeOrder()).asShortBuffer().apply {
                put(indices); position(0)
            }
    }

    fun updateHeights(frame: com.google.ar.core.Frame) {
        val depthImage = try {
            frame.acquireDepthImage16Bits()
        } catch (e: Exception) {
            return
        }

        val camera = frame.camera
        val intrinsics = camera.textureIntrinsics
        val focalLength = intrinsics.focalLength
        val principalPoint = intrinsics.principalPoint
        val res = intrinsics.imageDimensions

        // Map Viewport (Screen) to Sensor Coordinates
        depthUvBuffer.position(0)
        frame.transformCoordinates2d(
            com.google.ar.core.Coordinates2d.VIEW_NORMALIZED,
            displayUvBuffer,
            com.google.ar.core.Coordinates2d.IMAGE_NORMALIZED,
            depthUvBuffer
        )
        depthUvBuffer.position(0)

        val plane = depthImage.planes[0]
        val buffer = plane.buffer
        val rowStride = plane.rowStride
        val pixelStride = plane.pixelStride
        val depthWidth = depthImage.width
        val depthHeight = depthImage.height
        val cameraPose = camera.pose
        
        val pos = FloatArray(3)

        for (i in 0 until vertexCount) {
            val uS = depthUvBuffer.get(i * 2)
            val vS = depthUvBuffer.get(i * 2 + 1)

            // Edge-clamping for fullscreen depth sampling
            val col = (uS.coerceIn(0f, 1f) * (depthWidth - 1)).toInt()
            val row = (vS.coerceIn(0f, 1f) * (depthHeight - 1)).toInt()
            
            var meters = 5.0f
            val offset = row * rowStride + col * pixelStride
            if (offset + 1 < buffer.capacity()) {
                val mm = (buffer.get(offset).toInt() and 0xff) or
                        ((buffer.get(offset + 1).toInt() and 0xff) shl 8)
                if (mm > 0) meters = mm / 1000f
            }

            smoothMeters[i] += (meters - smoothMeters[i]) * depthLerp
            val d = smoothMeters[i]

            // PHYSICALLY ACCURATE UNPROJECTION:
            // Using Texture Intrinsics (focal length & principal point)
            // with Sensor Coordinates (uS, vS) to find the exact 3D ray.
            val z = -d
            val x = (uS * res[0] - principalPoint[0]) * d / focalLength[0]
            val y = -(vS * res[1] - principalPoint[1]) * d / focalLength[1]

            pos[0] = x; pos[1] = y; pos[2] = z
            val worldPos = cameraPose.transformPoint(pos)

            val idx = i * 3
            vertexBuffer.put(idx, worldPos[0])
            vertexBuffer.put(idx + 1, worldPos[1])
            vertexBuffer.put(idx + 2, worldPos[2])
        }
        
        vertexBuffer.position(0)
        depthImage.close()
    }
}
