package com.mal.meshterrain

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.google.ar.core.ArCoreApk
import com.google.ar.core.Config
import com.google.ar.core.Session
import com.google.ar.core.exceptions.UnavailableException
import android.opengl.GLSurfaceView
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.TextView

class MainActivity : AppCompatActivity() {

    private lateinit var glSurfaceView: GLSurfaceView
    private var arSession: Session? = null
    private val CAMERA_PERMISSION_CODE = 100

    private lateinit var startScreen: View
    private lateinit var arOverlay: View
    private lateinit var btnLaunch: Button
    private lateinit var btnStream: Button
    private lateinit var tvIp: TextView
    private lateinit var tvConnectionStatus: TextView

    // Top Popover Elements
    private lateinit var topPopover: View
    private lateinit var popoverText: TextView
    private lateinit var etPort: EditText
    private lateinit var btnPopoverConfirm: Button

    private var renderer: TerrainRenderer? = null
    private var streamServer: MjpegServer? = null
    private var isStreaming = false
    private var isScannerStarted = false
    
    private var activeNotificationMsg: String? = null
    private val hideNotificationRunnable = Runnable { hidePopover() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        
        // Prevent screen from turning off/dimming during use
        window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        
        glSurfaceView = findViewById(R.id.gl_surface_view)
        startScreen = findViewById(R.id.start_screen)
        arOverlay = findViewById(R.id.ar_overlay)
        btnLaunch = findViewById(R.id.btn_launch)
        btnStream = findViewById(R.id.btn_stream)
        tvIp = findViewById(R.id.tv_ip)
        tvConnectionStatus = findViewById(R.id.tv_connection_status)

        topPopover = findViewById(R.id.top_popover)
        popoverText = findViewById(R.id.popover_text)
        etPort = findViewById(R.id.et_port)
        btnPopoverConfirm = findViewById(R.id.btn_popover_confirm)

        glSurfaceView.setEGLContextClientVersion(2)

        btnLaunch.setOnClickListener {
            startScanner()
        }

        btnStream.setOnClickListener {
            if (isStreaming) {
                toggleStreaming(null)
            } else {
                showPortInputPopover()
            }
        }
        
        btnPopoverConfirm.setOnClickListener {
            val portStr = etPort.text.toString()
            val port = portStr.toIntOrNull() ?: 8081
            hidePopover()
            toggleStreaming(port)
        }
        
        streamServer = MjpegServer(8081).apply {
            setClientStatusListener { connected ->
                runOnUiThread {
                    if (connected && isStreaming) {
                        tvConnectionStatus.visibility = View.VISIBLE
                        showNotification("PC CONNECTED")
                    } else {
                        tvConnectionStatus.visibility = View.GONE
                        if (isStreaming) {
                            showNotification("PC DISCONNECTED")
                        }
                    }
                }
            }
        }
    }

    private fun showNotification(msg: String, durationMs: Long = 3000) {
        runOnUiThread {
            topPopover.removeCallbacks(hideNotificationRunnable)
            activeNotificationMsg = msg
            
            popoverText.text = msg
            etPort.visibility = View.GONE
            btnPopoverConfirm.visibility = View.GONE
            
            showPopover()
            
            topPopover.postDelayed(hideNotificationRunnable, durationMs)
        }
    }

    private fun showPortInputPopover() {
        topPopover.removeCallbacks(hideNotificationRunnable)
        popoverText.text = "SET PORT:"
        etPort.visibility = View.VISIBLE
        btnPopoverConfirm.visibility = View.VISIBLE
        etPort.setText("8081")
        showPopover()
        
        etPort.requestFocus()
        val imm = getSystemService(android.view.inputmethod.InputMethodManager::class.java)
        imm.showSoftInput(etPort, android.view.inputmethod.InputMethodManager.SHOW_IMPLICIT)
    }

    private fun showPopover() {
        topPopover.visibility = View.VISIBLE
        topPopover.post {
            // Pivot at the top center (where the camera hole is)
            topPopover.pivotX = topPopover.width / 2f
            topPopover.pivotY = 0f
            
            topPopover.animate()
                .alpha(1f)
                .scaleX(1f)
                .scaleY(1f)
                .translationY(10f) // Drop slightly from the hole
                .setDuration(500)
                .setInterpolator(android.view.animation.OvershootInterpolator(1.4f))
                .start()
        }
    }

    private fun hidePopover() {
        val imm = getSystemService(android.view.inputmethod.InputMethodManager::class.java)
        imm.hideSoftInputFromWindow(etPort.windowToken, 0)
        
        topPopover.animate()
            .alpha(0f)
            .scaleX(0.1f)
            .scaleY(0.1f)
            .translationY(0f) // Pull back into the hole
            .setDuration(400)
            .setInterpolator(android.view.animation.AnticipateInterpolator())
            .withEndAction { topPopover.visibility = View.GONE }
            .start()
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
        startScreen.visibility = View.GONE
        glSurfaceView.visibility = View.VISIBLE
        arOverlay.visibility = View.VISIBLE
        
        // IP and Port are initially hidden via XML (visibility: gone)
        
        @Suppress("DEPRECATION")
        window.decorView.systemUiVisibility = (View.SYSTEM_UI_FLAG_FULLSCREEN
                or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                or View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY)
    }

    private fun updateIpDisplay(port: Int) {
        val ips = getIPAddressesList()
        tvIp.text = "IPs:\n${ips.joinToString("\n")}\n(Port: $port)"
        tvIp.visibility = View.VISIBLE
    }

    private fun toggleStreaming(port: Int?) {
        if (port != null) {
            // Start Streaming
            isStreaming = true
            btnStream.text = "STOP STREAMING"
            btnStream.setBackgroundColor(android.graphics.Color.RED)
            
            streamServer?.start(port) { success ->
                runOnUiThread {
                    if (success) {
                        updateIpDisplay(port)
                        showNotification("SERVER LIVE ON PORT $port")
                    } else {
                        isStreaming = false
                        btnStream.text = "STREAM TO PC"
                        btnStream.setBackgroundColor(android.graphics.Color.parseColor("#00E676"))
                        tvIp.visibility = View.GONE
                        showNotification("PORT $port BLOCKED!")
                    }
                }
            }
            renderer?.setStreamingListener { bitmap ->
                streamServer?.pushFrame(bitmap)
            }
        } else {
            // Stop Streaming
            isStreaming = false
            btnStream.text = "STREAM TO PC"
            btnStream.setBackgroundColor(android.graphics.Color.parseColor("#00E676"))
            tvIp.visibility = View.GONE
            tvConnectionStatus.visibility = View.GONE
            renderer?.setStreamingListener(null)
            streamServer?.stop()
            showNotification("STREAMING TERMINATED")
        }
    }

    private fun getIPAddressesList(): List<String> {
        val list = mutableListOf<String>()
        try {
            val interfaces = java.net.NetworkInterface.getNetworkInterfaces()
            while (interfaces.hasMoreElements()) {
                val networkInterface = interfaces.nextElement()
                val addresses = networkInterface.inetAddresses
                while (addresses.hasMoreElements()) {
                    val address = addresses.nextElement()
                    if (!address.isLoopbackAddress && address is java.net.Inet4Address) {
                        val ip = address.hostAddress ?: continue
                        if (networkInterface.name.contains("wlan") || networkInterface.name.contains("ap")) {
                            list.add(0, ip)
                        } else {
                            list.add(ip)
                        }
                    }
                }
            }
        } catch (e: Exception) {}
        return list
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
                showNotification("CAMERA PERMISSION DENIED")
            }
        }
    }

    private fun checkArCoreAndDepth() {
        try {
            val availability = ArCoreApk.getInstance().checkAvailability(this)
            if (!availability.isSupported) {
                showNotification("ARCORE NOT SUPPORTED")
                isScannerStarted = false
                return
            }

            val session = Session(this)
            val isDepthSupported = session.isDepthModeSupported(Config.DepthMode.AUTOMATIC)

            if (isDepthSupported) {
                val config = session.config
                config.depthMode = Config.DepthMode.AUTOMATIC
                session.configure(config)
                showNotification("DEPTH API ENABLED")
            } else {
                showNotification("DEPTH NOT SUPPORTED")
            }

            arSession = session
            val rendererInstance = TerrainRenderer(session)
            renderer = rendererInstance
            glSurfaceView.setRenderer(rendererInstance)
            glSurfaceView.renderMode = GLSurfaceView.RENDERMODE_CONTINUOUSLY

            glSurfaceView.onResume()
            session.resume()

        } catch (e: UnavailableException) {
            showNotification("ARCORE UNAVAILABLE")
            isScannerStarted = false
        } catch (e: Exception) {
            showNotification("INIT ERROR: ${e.message}")
            isScannerStarted = false
        }
    }

    override fun onDestroy() {
        streamServer?.stop()
        arSession?.close()
        arSession = null
        super.onDestroy()
    }

    override fun onResume() {
        super.onResume()
        if (isScannerStarted && arSession != null) {
            glSurfaceView.onResume()
            arSession?.resume()
        }
    }

    override fun onPause() {
        super.onPause()
        if (isScannerStarted && arSession != null) {
            arSession?.pause()
            glSurfaceView.onPause()
        }
    }
}
