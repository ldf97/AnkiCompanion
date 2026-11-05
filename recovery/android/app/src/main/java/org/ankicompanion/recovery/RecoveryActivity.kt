package org.ankicompanion.recovery

import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.content.FileProvider
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/** Frozen independent safety hatch. This never invokes AnkiCompanion code. */
class RecoveryActivity : Activity() {
    private val base="https://github.com/ldf97/AnkiCompanion/releases/latest/download/"
    private val expectedPackage="org.ankicompanion.app"
    private val officialSigner="c6a5e9f1804fdf1083c69e36e03e3a424a0e630e357b573d8a523eea09cea004"
    private val client=OkHttpClient.Builder().connectTimeout(15,TimeUnit.SECONDS)
        .readTimeout(90,TimeUnit.SECONDS).followRedirects(true).build()
    private val executor=Executors.newSingleThreadExecutor()
    private lateinit var status:TextView
    private lateinit var repair:Button
    private var readyFile:File?=null
    private var requestingPermission=false

    override fun onCreate(savedInstanceState:Bundle?) {
        super.onCreate(savedInstanceState)
        val root=LinearLayout(this).apply {
            orientation=LinearLayout.VERTICAL
            setPadding(24,40,24,24)
            setBackgroundColor(Color.rgb(16,24,36))
        }
        fun label(value:String,size:Float)=TextView(this).apply {
            text=value;textSize=size;setTextColor(Color.WHITE)
            gravity=Gravity.CENTER;setPadding(8,14,8,14)
        }
        root.addView(label("AnkiCompanion Recovery",24f))
        root.addView(label("Independent safety hatch\nWorks even if AnkiCompanion cannot start.\nYour study data is not deleted.",16f))
        repair=Button(this).apply {
            text="Repair / reinstall AnkiCompanion"
            setOnClickListener{retrieve()}
        }
        root.addView(repair)
        status=label("Checks the official GitHub release and verifies its APK.",14f)
        root.addView(status)
        setContentView(root)
    }
    private fun show(value:String){runOnUiThread{status.text=value}}
    private fun fetchManifest():JSONObject {
        client.newCall(Request.Builder().url(base+"update.json").get().build()).execute().use {r->
            require(r.isSuccessful){"GitHub HTTP ${r.code}"}
            require(r.request.url.isHttps){"Insecure redirect"}
            val data=(r.body ?: error("Missing manifest")).bytes()
            require(data.size<=128*1024){"Release manifest too large"}
            return JSONObject(String(data,Charsets.UTF_8))
        }
    }
    private fun signingFingerprint(info:android.content.pm.PackageInfo):String {
        val signatures=if(Build.VERSION.SDK_INT>=28)
            info.signingInfo?.apkContentsSigners else info.signatures
        val certificate=signatures?.firstOrNull() ?: error("No signer in APK")
        return MessageDigest.getInstance("SHA-256").digest(certificate.toByteArray())
            .joinToString(""){"%02x".format(it)}
    }
    private fun retrieve(){
        repair.isEnabled=false
        show("Checking GitHub stable release…")
        executor.execute{
            try {
                val manifest=fetchManifest()
                require(manifest.getInt("schema_version")==1){"Invalid release manifest"}
                val asset=manifest.getJSONObject("assets").getJSONObject("android")
                val name=asset.getString("filename")
                val size=asset.getLong("size")
                val expected=asset.getString("sha256").lowercase()
                require(name=="AnkiCompanion-Android.apk" && size in 10000..(200L*1024*1024)
                    && expected.matches(Regex("[0-9a-f]{64}"))){"Invalid APK release metadata"}
                val temp=File(cacheDir,"recovery.partial")
                val target=File(cacheDir,"recovery.apk")
                val digest=MessageDigest.getInstance("SHA-256")
                var total=0L
                var last=-1
                try {
                    show("Downloading verified APK…")
                    client.newCall(Request.Builder().url(base+name).get().build()).execute().use {r->
                        require(r.isSuccessful){"APK download HTTP ${r.code}"}
                        require(r.request.url.isHttps){"Insecure download redirect"}
                        (r.body ?: error("No APK content")).byteStream().use {input->
                            temp.outputStream().use {output->
                                val buffer=ByteArray(65536)
                                while(true){
                                    val count=input.read(buffer)
                                    if(count<0)break
                                    total+=count
                                    require(total<=size){"APK larger than declared"}
                                    digest.update(buffer,0,count)
                                    output.write(buffer,0,count)
                                    val pct=(total*100/size).toInt()
                                    if(pct!=last){last=pct;show("Downloading: $pct%")}
                                }
                            }
                        }
                    }
                    val actual=digest.digest().joinToString(""){"%02x".format(it)}
                    require(total==size && actual==expected){"APK checksum mismatch"}
                    require(temp.renameTo(target)){"Could not finalize APK"}
                    val flags=if(Build.VERSION.SDK_INT>=28)
                        PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES
                    val info=packageManager.getPackageArchiveInfo(target.absolutePath,flags)
                        ?: error("Invalid downloaded APK")
                    require(info.packageName==expectedPackage){"Wrong Android package"}
                    require(signingFingerprint(info)==officialSigner){"APK has incorrect signing certificate"}
                    readyFile=target
                    show("Verified official APK. Opening system installer…")
                    runOnUiThread{installReady()}
                } finally {temp.delete()}
            } catch(e:Exception){
                show("Recovery stopped safely: ${e.message}")
            } finally {runOnUiThread{repair.isEnabled=true}}
        }
    }
    private fun installReady(){
        val file=readyFile ?: return
        if(Build.VERSION.SDK_INT>=26 && !packageManager.canRequestPackageInstalls()){
            requestingPermission=true
            show("Allow installations from Recovery, then return.")
            startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                Uri.parse("package:$packageName")))
            return
        }
        requestingPermission=false
        val uri=FileProvider.getUriForFile(this,"$packageName.files",file)
        startActivity(Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri,"application/vnd.android.package-archive")
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_GRANT_READ_URI_PERMISSION)
        })
    }
    override fun onResume(){
        super.onResume()
        if(requestingPermission && (Build.VERSION.SDK_INT<26 || packageManager.canRequestPackageInstalls())){
            requestingPermission=false
            window.decorView.post{installReady()}
        }
    }
    override fun onDestroy(){executor.shutdown();super.onDestroy()}
}
