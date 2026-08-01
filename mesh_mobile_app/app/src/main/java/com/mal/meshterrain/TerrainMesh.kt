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
    private val smoothVertices = FloatArray(vertexCount * 3)
    private val depthLerp = 0.2f // Higher = more responsive, Lower = more "Venom" liquid look

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

        // Align coordinates to the camera image for fullscreen stability
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
            val uDepth = depthUvBuffer.get(i * 2)
            val vDepth = depthUvBuffer.get(i * 2 + 1)

            var meters = 6.0f 
            if (uDepth in 0f..1f && vDepth in 0f..1f) {
                val col = (uDepth * (depthWidth - 1)).toInt()
                val row = (vDepth * (depthHeight - 1)).toInt()
                val offset = row * rowStride + col * pixelStride
                if (offset + 1 < buffer.capacity()) {
                    val mm = (buffer.get(offset).toInt() and 0xff) or
                            ((buffer.get(offset + 1).toInt() and 0xff) shl 8)
                    if (mm > 0) meters = mm / 1000f
                }
            }

            // Smooth depth noise
            smoothMeters[i] += (meters - smoothMeters[i]) * depthLerp
            val d = smoothMeters[i]

            // Unproject using Display Viewport UVs to keep it fullscreen
            val screenU = displayUvBuffer.get(i * 2)
            val screenV = displayUvBuffer.get(i * 2 + 1)
            
            val z = -d
            val x = (screenU * res[0] - principalPoint[0]) * d / focalLength[0]
            val y = -(screenV * res[1] - principalPoint[1]) * d / focalLength[1]

            pos[0] = x; pos[1] = y; pos[2] = z
            val worldPos = cameraPose.transformPoint(pos)

            val idx = i * 3
            smoothVertices[idx] += (worldPos[0] - smoothVertices[idx]) * 0.3f
            smoothVertices[idx + 1] += (worldPos[1] - smoothVertices[idx + 1]) * 0.3f
            smoothVertices[idx + 2] += (worldPos[2] - smoothVertices[idx + 2]) * 0.3f
        }
        
        vertexBuffer.position(0)
        vertexBuffer.put(smoothVertices)
        vertexBuffer.position(0)
        depthImage.close()
    }
}
