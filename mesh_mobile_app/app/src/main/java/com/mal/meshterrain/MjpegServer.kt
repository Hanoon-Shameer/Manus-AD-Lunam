package com.mal.meshterrain

import android.graphics.Bitmap
import android.util.Log
import java.io.BufferedReader
import java.io.ByteArrayOutputStream
import java.io.InputStreamReader
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.Executors

class MjpegServer(private var port: Int) {

    private var serverSocket: ServerSocket? = null
    private val serverExecutor = Executors.newSingleThreadExecutor()
    private val pushExecutor = Executors.newSingleThreadExecutor() 
    private val pushSemaphore = java.util.concurrent.Semaphore(1)
    private val clients = mutableListOf<Socket>()
    private var isRunning = false
    private val boundary = "boundary123"
    private var onClientStatusChanged: ((Boolean) -> Unit)? = null
    
    fun setClientStatusListener(listener: (Boolean) -> Unit) {
        onClientStatusChanged = listener
    }

    fun start(customPort: Int? = null, onStarted: (Boolean) -> Unit) {
        if (isRunning) return
        customPort?.let { this.port = it }
        isRunning = true
        serverExecutor.execute {
            try {
                serverSocket = ServerSocket(port, 5, java.net.InetAddress.getByName("0.0.0.0"))
                Log.d("MjpegServer", "MJPEG Server listening on 0.0.0.0:$port")
                onStarted(true)
                while (isRunning) {
                    val socket = serverSocket?.accept()
                    socket?.let { handleClient(it) }
                }
            } catch (e: Exception) {
                if (isRunning) {
                    Log.e("MjpegServer", "Server error", e)
                    onStarted(false)
                }
            }
        }
    }

    fun stop() {
        isRunning = false
        try {
            serverSocket?.close()
        } catch (e: Exception) {}
        synchronized(clients) {
            clients.forEach { try { it.close() } catch (e: Exception) {} }
            clients.clear()
            onClientStatusChanged?.invoke(false)
        }
    }

    private fun handleClient(socket: Socket) {
        Thread {
            try {
                Log.d("MjpegServer", "New connection from ${socket.inetAddress}")
                
                // CRITICAL FOR OPENCV: Consume the entire HTTP request headers
                val reader = BufferedReader(InputStreamReader(socket.getInputStream()))
                var line: String? = reader.readLine()
                while (line != null && line.isNotBlank()) {
                    line = reader.readLine()
                }
                
                val outputStream = socket.getOutputStream()
                val header = ("HTTP/1.0 200 OK\r\n" +
                        "Server: MeshTerrain\r\n" +
                        "Connection: close\r\n" +
                        "Max-Age: 0\r\n" +
                        "Expires: 0\r\n" +
                        "Cache-Control: no-cache, private\r\n" +
                        "Pragma: no-cache\r\n" +
                        "Content-Type: multipart/x-mixed-replace; boundary=$boundary\r\n\r\n")
                
                outputStream.write(header.toByteArray())
                outputStream.flush()

                synchronized(clients) {
                    clients.add(socket)
                    if (clients.size == 1) {
                        onClientStatusChanged?.invoke(true)
                    }
                }
            } catch (e: Exception) {
                Log.e("MjpegServer", "Error handling client", e)
                try { socket.close() } catch (ex: Exception) {}
            }
        }.start()
    }

    fun pushFrame(bitmap: Bitmap) {
        if (!isRunning) {
            bitmap.recycle()
            return
        }
        
        synchronized(clients) {
            if (clients.isEmpty()) {
                bitmap.recycle()
                return
            }
        }

        if (!pushSemaphore.tryAcquire()) {
            bitmap.recycle()
            return
        }

        pushExecutor.execute {
            try {
                val stream = ByteArrayOutputStream()
                bitmap.compress(Bitmap.CompressFormat.JPEG, 35, stream)
                val jpegData = stream.toByteArray()
                bitmap.recycle()

                // Classic MJPEG Frame Header
                val frameHeader = ("--$boundary\r\n" +
                        "Content-Type: image/jpeg\r\n" +
                        "Content-Length: ${jpegData.size}\r\n\r\n")

                synchronized(clients) {
                    val iterator = clients.iterator()
                    while (iterator.hasNext()) {
                        val socket = iterator.next()
                        try {
                            val os = socket.getOutputStream()
                            os.write(frameHeader.toByteArray())
                            os.write(jpegData)
                            os.write("\r\n".toByteArray())
                            os.flush()
                        } catch (e: Exception) {
                            Log.d("MjpegServer", "Client disconnected")
                            try { socket.close() } catch (ex: Exception) {}
                            iterator.remove()
                            if (clients.isEmpty()) {
                                onClientStatusChanged?.invoke(false)
                            }
                        }
                    }
                }
            } catch (e: Exception) {
                Log.e("MjpegServer", "Error pushing frame", e)
            } finally {
                pushSemaphore.release()
            }
        }
    }
}
