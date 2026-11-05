package com.ankicompanion.ponglab

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.graphics.Color
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.content.FileProvider
import java.io.File
import java.util.concurrent.Executors

class MainActivity:Activity() {
    private val worker=Executors.newSingleThreadExecutor()
    private lateinit var status:TextView
    private lateinit var updateButton:Button
    private var staged:File?=null
    private var pendingPermission=false
    override fun onCreate(savedInstanceState:Bundle?){
        super.onCreate(savedInstanceState)
        val root=LinearLayout(this).apply {
            orientation=LinearLayout.VERTICAL
            setBackgroundColor(Color.rgb(14,19,36))
            setPadding(20,28,20,20)
        }
        val title=TextView(this).apply {
            text="🏓 Pong Update Lab · v${BuildConfig.VERSION_NAME}"
            setTextColor(Color.WHITE);textSize=21f;gravity=Gravity.CENTER
        }
        root.addView(title,LinearLayout.LayoutParams(-1,66))
        val game=PongView(this)
        root.addView(game,LinearLayout.LayoutParams(-1,0,1f))
        val actions=LinearLayout(this).apply{gravity=Gravity.CENTER}
        updateButton=Button(this).apply{
            text="Check for update"
            setOnClickListener{beginUpdate()}
        }
        actions.addView(updateButton)
        val restart=Button(this).apply{text="Restart game";setOnClickListener{game.restart()}}
        actions.addView(restart)
        root.addView(actions)
        status=TextView(this).apply{
            text="Move the green paddle with your finger. First to 7 wins."
            textSize=14f;gravity=Gravity.CENTER;setTextColor(Color.rgb(192,210,232))
            setPadding(12,12,12,8)
        }
        root.addView(status,LinearLayout.LayoutParams(-1,92))
        setContentView(root)
    }
    private fun show(message:String){runOnUiThread{status.text=message}}
    private fun beginUpdate(){
        updateButton.isEnabled=false
        show("Checking GitHub for Pong updates…")
        worker.execute{
            try{
                val offer=PongUpdater.check(this)
                if(offer==null){
                    show("Pong v${BuildConfig.VERSION_NAME} is up to date.")
                } else {
                    show("Updating to Pong ${offer.version}…")
                    val path=PongUpdater.download(this,offer){percent->
                        show("Downloading Pong ${offer.version}: $percent%")
                    }
                    staged=path
                    show("Download verified. Opening Android installer…")
                    runOnUiThread{installStaged()}
                }
            }catch(e:Exception){show("Update failed: ${e.message}")}
            finally{runOnUiThread{updateButton.isEnabled=true}}
        }
    }
    private fun installStaged(){
        val file=staged ?: return
        if(Build.VERSION.SDK_INT>=26 && !packageManager.canRequestPackageInstalls()){
            pendingPermission=true
            show("Allow Pong to install updates, then return to this screen.")
            startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                Uri.parse("package:$packageName")))
            return
        }
        pendingPermission=false
        val uri=FileProvider.getUriForFile(this,"$packageName.files",file)
        startActivity(Intent(Intent.ACTION_VIEW).apply{
            setDataAndType(uri,"application/vnd.android.package-archive")
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_GRANT_READ_URI_PERMISSION)
        })
    }
    override fun onResume(){
        super.onResume()
        if(pendingPermission && (Build.VERSION.SDK_INT<26 || packageManager.canRequestPackageInstalls())){
            pendingPermission=false
            window.decorView.post{installStaged()}
        }
    }
    override fun onDestroy(){worker.shutdown();super.onDestroy()}
}
