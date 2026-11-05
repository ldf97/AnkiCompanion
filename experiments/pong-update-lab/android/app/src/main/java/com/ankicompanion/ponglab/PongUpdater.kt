package com.ankicompanion.ponglab

import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest
import java.util.concurrent.TimeUnit

/**
 * Mihon's update pathway: direct public GitHub release, OkHttp download
 * with progress, then Android's native APK installer (called by MainActivity).
 * The Pong-specific manifest is isolated from AnkiCompanion's releases.
 */
object PongUpdater {
    private const val CHANNEL = "https://github.com/ldf97/AnkiCompanion/releases/download/pong-update-lab/"
    private const val MANIFEST = CHANNEL + "pong-android.json"
    private const val ASSET = CHANNEL + "PongLab-Android.apk"
    private val client = OkHttpClient.Builder().connectTimeout(15,TimeUnit.SECONDS)
        .readTimeout(60,TimeUnit.SECONDS).followRedirects(true).build()
    data class Offer(val version:String,val code:Long,val size:Long,val sha256:String)
    private fun response(url:String):ByteArray {
        client.newCall(Request.Builder().url(url).get().build()).execute().use { r ->
            require(r.isSuccessful) { "GitHub returned HTTP ${r.code}" }
            return (r.body ?: error("Empty GitHub response")).bytes()
        }
    }
    fun check(context:Context): Offer? {
        val manifest=JSONObject(String(response(MANIFEST),Charsets.UTF_8))
        val version=manifest.getString("version")
        val code=manifest.getLong("version_code")
        val size=manifest.getLong("size")
        val sha=manifest.getString("sha256").lowercase()
        require(version.matches(Regex("[0-9]+\\.[0-9]+\\.[0-9]+"))) { "Invalid version" }
        require(sha.matches(Regex("[0-9a-f]{64}"))) { "Invalid SHA-256" }
        require(size>10000L && size<80L*1024L*1024L) { "Invalid APK size" }
        return if(code>BuildConfig.VERSION_CODE) Offer(version,code,size,sha) else null
    }
    fun download(context:Context,offer:Offer,onProgress:(Int)->Unit):File {
        val target=File(context.cacheDir,"pong-update.apk")
        val temp=File(context.cacheDir,"pong-update.apk.partial")
        val digest=MessageDigest.getInstance("SHA-256")
        var total=0L
        var last=-1
        try {
            // Mihon's OkHttp streaming-body -> file download pattern.
            client.newCall(Request.Builder().url(ASSET).get().build()).execute().use { r ->
                require(r.isSuccessful) { "APK HTTP ${r.code}" }
                require(r.request.url.isHttps) { "Insecure redirect" }
                val body=r.body ?: error("No APK body")
                body.byteStream().use { input -> temp.outputStream().use { output ->
                    val buffer=ByteArray(65536)
                    while(true){
                        val count=input.read(buffer)
                        if(count<0)break
                        total+=count
                        require(total<=offer.size){"Download exceeds expected size"}
                        digest.update(buffer,0,count)
                        output.write(buffer,0,count)
                        val percent=(total*100/offer.size).toInt()
                        if(percent!=last){last=percent;onProgress(percent)}
                    }
                }}
            }
            val sha=digest.digest().joinToString(""){"%02x".format(it)}
            require(total==offer.size && sha==offer.sha256){"Downloaded APK checksum mismatch"}
            require(temp.renameTo(target)){"Could not save APK"}
            val flags=if(Build.VERSION.SDK_INT>=28)PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES
            val info=context.packageManager.getPackageArchiveInfo(target.absolutePath,flags) ?: error("Invalid APK")
            require(info.packageName==context.packageName){"Wrong package name"}
            val code=if(Build.VERSION.SDK_INT>=28)info.longVersionCode else info.versionCode.toLong()
            require(code==offer.code && code>BuildConfig.VERSION_CODE){"Wrong APK version"}
            val current=context.packageManager.getPackageInfo(context.packageName,flags)
            val previous=(if(Build.VERSION.SDK_INT>=28)
                current.signingInfo?.signingCertificateHistory ?: current.signingInfo?.apkContentsSigners
                else current.signatures)?.map{it.toCharsString()}?.toSet()
            val incoming=(if(Build.VERSION.SDK_INT>=28)
                info.signingInfo?.signingCertificateHistory ?: info.signingInfo?.apkContentsSigners
                else info.signatures)?.map{it.toCharsString()}?.toSet()
            require(!previous.isNullOrEmpty() && !incoming.isNullOrEmpty() && previous.intersect(incoming).isNotEmpty()){
                "This APK has a different signing identity; original installation was preserved."
            }
            return target
        } finally {temp.delete()}
    }
}
