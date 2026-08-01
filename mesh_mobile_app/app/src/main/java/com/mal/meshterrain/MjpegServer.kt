package com.mal.meshterrain

import android.graphics.Bitmap
import java.io.ByteArrayOutputStream
import java.io.OutputStream
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.Executors

class MjpegServer(private val port: Int) {

    private var serverSocket: ServerSocket? = null
    private val serverExecutor = Executors.newSingleThreadExecutor()
    private val pushExecutor = Executors.newFixedThreadPool(2)
    private val clients = mutableListOf<Socket>()
    private var isRunning = false

    fun start() {
        if (isRunning) return
        isRunning = true
        serverExecutor.execute {
            try {
                serverSocket = ServerSocket(port)
                android.util.Log.d("MjpegServer", "Server started on port $port")
                while (isRunning) {
                    val socket = serverSocket?.accept()
                    socket?.let { handleClient(it) }
                }
            } catch (e: Exception) {
                if (isRunning) e.printStackTrace()
            }
        }
    }

    fun stop() {
        isRunning = false
        serverSocket?.close()
        synchronized(clients) {
            clients.forEach { try { it.close() } catch (e: Exception) {} }
            clients.clear()
        }
    }

    private fun handleClient(socket: Socket) {
        java.lang.Thread {
            try {
                android.util.Log.d("MjpegServer", "New client connected: ${socket.inetAddress}")
                val outputStream = socket.getOutputStream()
                outputStream.write(("HTTP/1.0 200 OK\r\n" +
                        "Server: MeshTerrain\r\n" +
                        "Connection: close\r\n" +
                        "Max-Age: 0\r\n" +
                        "Expires: 0\r\n" +
                        "Cache-Control: no-cache, private\r\n" +
                        "Pragma: no-cache\r\n" +
                        "Content-Type: multipart/x-mixed-replace; boundary=7b3cc56e5f51db803f790dad720ed50a\r\n\r\n").toByteArray())
                outputStream.flush()

                synchronized(clients) {
                    clients.add(socket)
                }
            } catch (e: Exception) {
                android.util.Log.e("MjpegServer", "Error handling client", e)
                try { socket.close() } catch (ex: Exception) {}
            }
        }.start()
    }

    fun pushFrame(bitmap: Bitmap) {
        if (!isRunning) return
        
        synchronized(clients) {
            if (clients.isEmpty()) {
                bitmap.recycle()
                return
            }
        }

        pushExecutor.execute {
            val stream = ByteArrayOutputStream()
            bitmap.compress(Bitmap.CompressFormat.JPEG, 50, stream)
            val jpegData = stream.toByteArray()
            bitmap.recycle()
            
            synchronized(clients) {
                val iterator = clients.iterator()
                while (iterator.hasNext()) {
                    val socket = iterator.next()
                    try {
                        val outputStream = socket.getOutputStream()
                        outputStream.write(("\r\n--7b3cc56e5f51db803f790dad720ed50a\r\n" +
                                "Content-Type: image/jpeg\r\n" +
                                "Content-Length: ${jpegData.size}\r\n\r\n").toByteArray())
                        outputStream.write(jpegData)
                        outputStream.flush()
                    } catch (e: Exception) {
                        try { socket.close() } catch (ex: Exception) {}
                        iterator.remove()
                    }
                }
            }
        }
    }
}
