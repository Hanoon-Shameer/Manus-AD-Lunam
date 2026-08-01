package com.mal.meshterrain

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.util.Log
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.google.ar.core.ArCoreApk
import com.google.ar.core.Config
import com.google.ar.core.Session
import com.google.ar.core.exceptions.UnavailableException
import android.opengl.GLSurfaceView

class MainActivity : AppCompatActivity() {

    private lateinit var glSurfaceView: GLSurfaceView
    private var arSession: Session? = null
    private val CAMERA_PERMISSION_CODE = 100

    private lateinit var startScreen: android.view.View
    private lateinit var arOverlay: android.view.View
    private lateinit var btnLaunch: android.widget.Button
    private lateinit var btnStream: android.widget.Button
    private lateinit var tvIp: android.widget.TextView

    private var renderer: TerrainRenderer? = null
    private var streamServer: MjpegServer? = null
    private var isStreaming = false
    private var isScannerStarted = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        
        glSurfaceView = findViewById(R.id.gl_surface_view)
        startScreen = findViewById(R.id.start_screen)
        arOverlay = findViewById(R.id.ar_overlay)
        btnLaunch = findViewById(R.id.btn_launch)
        btnStream = findViewById(R.id.btn_stream)
        tvIp = findViewById(R.id.tv_ip)

        glSurfaceView.setEGLContextClientVersion(2)

        btnLaunch.setOnClickListener {
            startScanner()
        }

        btnStream.setOnClickListener {
            toggleStreaming()
        }
        
        streamServer = MjpegServer(8080)
    }

    private fun startScanner() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
            != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(
                this,
                arrayOf(Manifest.permission.CAMERA),
                CAMERA_PERMISSION_CODE
            )
        } else {
            if (!isScannerStarted) {
                isScannerStarted = true
                checkArCoreAndDepth()
            }
            showArView()
        }
    }

    private fun showArView() {
        startScreen.visibility = android.view.View.GONE
        glSurfaceView.visibility = android.view.View.VISIBLE
        arOverlay.visibility = android.view.View.VISIBLE
        tvIp.text = "IP: ${getIPAddress()}"
        
        // Hide status and navigation bars for a clean look
        @Suppress("DEPRECATION")
        window.decorView.systemUiVisibility = (android.view.View.SYSTEM_UI_FLAG_FULLSCREEN
                or android.view.View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                or android.view.View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY)
    }

    private fun toggleStreaming() {
        isStreaming = !isStreaming
        if (isStreaming) {
            btnStream.text = "STOP STREAMING"
            btnStream.setBackgroundColor(android.graphics.Color.RED)
            streamServer?.start()
            renderer?.setStreamingListener { bitmap ->
                streamServer?.pushFrame(bitmap)
            }
            logAndToast("Streaming started at http://${getIPAddress()}:8080")
        } else {
            btnStream.text = "STREAM TO PC"
            btnStream.setBackgroundColor(android.graphics.Color.parseColor("#00E676"))
            renderer?.setStreamingListener(null)
            streamServer?.stop()
            logAndToast("Streaming stopped")
        }
    }

    private fun getIPAddress(): String {
        try {
            val interfaces = java.net.NetworkInterface.getNetworkInterfaces()
            val list = mutableListOf<java.net.InetAddress>()
            while (interfaces.hasMoreElements()) {
                val networkInterface = interfaces.nextElement()
                val addresses = networkInterface.inetAddresses
                while (addresses.hasMoreElements()) {
                    val address = addresses.nextElement()
                    if (!address.isLoopbackAddress && address is java.net.Inet4Address) {
                        // Prefer wlan0 or similar Wi-Fi interfaces
                        if (networkInterface.name.contains("wlan") || networkInterface.name.contains("ap")) {
                            return address.hostAddress ?: "Unknown"
                        }
                        list.add(address)
                    }
                }
            }
            return if (list.isNotEmpty()) list[0].hostAddress ?: "Unknown" else "Unknown"
        } catch (e: Exception) {
            e.printStackTrace()
        }
        return "Unknown"
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == CAMERA_PERMISSION_CODE) {
            if (grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                startScanner()
            } else {
                logAndToast("Camera permission denied — cannot proceed.")
            }
        }
    }

    private fun checkArCoreAndDepth() {
        try {
            val availability = ArCoreApk.getInstance().checkAvailability(this)
            if (!availability.isSupported) {
                logAndToast("ARCore NOT supported on this device.")
                isScannerStarted = false
                return
            }

            val session = Session(this)
            val isDepthSupported = session.isDepthModeSupported(Config.DepthMode.AUTOMATIC)

            if (isDepthSupported) {
                val config = session.config
                config.depthMode = Config.DepthMode.AUTOMATIC
                session.configure(config)
                logAndToast("Depth API SUPPORTED — enabled.")
            } else {
                logAndToast("Depth API NOT supported on this device.")
            }

            arSession = session
            val rendererInstance = TerrainRenderer(session)
            renderer = rendererInstance
            glSurfaceView.setRenderer(rendererInstance)
            glSurfaceView.renderMode = GLSurfaceView.RENDERMODE_CONTINUOUSLY

            // Explicitly resume since we're already in the foreground
            glSurfaceView.onResume()
            session.resume()

        } catch (e: UnavailableException) {
            logAndToast("ARCore unavailable: ${e.message}")
            isScannerStarted = false
        } catch (e: Exception) {
            logAndToast("Error setting up ARCore: ${e.message}")
            isScannerStarted = false
        }
    }

    private fun logAndToast(msg: String) {
        Log.d("MeshTerrain", msg)
        Toast.makeText(this, msg, Toast.LENGTH_LONG).show()
    }

    override fun onDestroy() {
        streamServer?.stop()
        arSession?.close()
        arSession = null
        super.onDestroy()
    }

    override fun onResume() {
        super.onResume()
        if (isScannerStarted) {
            glSurfaceView.onResume()
            arSession?.resume()
        }
    }

    override fun onPause() {
        super.onPause()
        if (isScannerStarted) {
            arSession?.pause()
            glSurfaceView.onPause()
        }
    }
}
