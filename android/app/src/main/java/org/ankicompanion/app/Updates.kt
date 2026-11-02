package org.ankicompanion.app

import android.app.Activity
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import org.json.JSONObject
import java.io.File

object Updates {
    fun check(context:Context,api:Api,force:Boolean=false):JSONObject? {
        val store=Storage(context);val cached=store.load("update.json")
        if(!force && cached!=null && System.currentTimeMillis()-cached.optLong("checked_ms")<60*60*1000)return cached
        // Updates are fetched directly from the public release channel,
        // even when the owner's Windows server is asleep or unreachable.
        val result=try{githubRelease()}catch(e:java.io.FileNotFoundException){
            JSONObject().put("configured",true).put("available",false).put("message","No stable signed release has been published")
        }
        result.put("checked_ms",System.currentTimeMillis());store.save("update.json",result);store.setSetting("update_error","")
        if(result.optBoolean("available"))notify(context,result)
        return result
    }
    private fun githubRelease():JSONObject {
        val request=java.net.URL("https://github.com/ldf97/AnkiCompanion/releases/latest/download/update.json").openConnection() as java.net.HttpURLConnection
        request.connectTimeout=12000;request.readTimeout=15000
        val data=request.inputStream.use{source->
            val out=java.io.ByteArrayOutputStream()
            val buffer=ByteArray(8192)
            while(true){val n=source.read(buffer);if(n<0)break
                require(out.size()+n<=128*1024){"Release manifest too large"}
                out.write(buffer,0,n)
            }
            out.toByteArray()
        }
        val manifest=JSONObject(String(data,Charsets.UTF_8))
        require(manifest.getInt("schema_version")==1){"Invalid release manifest"}
        val version=manifest.getString("version")
        require(Regex("[0-9]+\\.[0-9]+\\.[0-9]+").matches(version)){"Invalid release version"}
        val build=manifest.getInt("build")
        if(!manifest.getJSONObject("assets").has("android"))return JSONObject()
            .put("configured",true).put("available",false)
            .put("message","Android signed update not yet published")
        val asset=manifest.getJSONObject("assets").getJSONObject("android")
        val name=asset.getString("filename")
        require(Regex("[A-Za-z0-9_.-]+\\.apk").matches(name)){"Invalid release APK name"}
        require(Regex("[0-9a-f]{64}").matches(asset.getString("sha256"))){"Invalid release checksum"}
        val size=asset.getLong("size")
        require(size in 1..(200L*1024*1024)){"Invalid release size"}
        return JSONObject().put("configured",true).put("available",build>BuildConfig.VERSION_CODE)
            .put("version",version).put("build",build).put("filename",name)
            .put("size",size).put("sha256",asset.getString("sha256"))
            .put("download_url","https://github.com/ldf97/AnkiCompanion/releases/latest/download/"+name)
            .put("message",if(build>BuildConfig.VERSION_CODE)"Update available" else "Up to date")
    }
    private fun notify(context:Context,result:JSONObject) {
        if(Build.VERSION.SDK_INT>=33 && context.checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)return
        val manager=context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel("updates","App updates",NotificationManager.IMPORTANCE_DEFAULT))
        val intent=PendingIntent.getActivity(context,30,Intent(context,MainActivity::class.java).putExtra("updates",true),PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val notice=android.app.Notification.Builder(context,"updates").setSmallIcon(R.drawable.app_icon).setContentTitle("Anki Companion update available")
            .setContentText("Version "+result.optString("version")+" · tap to update").setContentIntent(intent).setAutoCancel(true).build()
        manager.notify(30,notice)
    }
    fun download(context:Context,api:Api,release:JSONObject):File {
        require(release.getBoolean("available")){"No update available"}
        val dest=File(context.filesDir,"updates/companion-update.apk")
        if(release.has("download_url")) {
            val address=release.getString("download_url")
            require(address.startsWith("https://github.com/ldf97/AnkiCompanion/releases/latest/download/")){"Untrusted update source"}
            val temp=File(dest.path+".partial")
            dest.parentFile?.mkdirs()
            try {
                val digest=java.security.MessageDigest.getInstance("SHA-256")
                var total=0L
                (java.net.URL(address).openConnection() as java.net.HttpURLConnection).apply{
                    connectTimeout=15000;readTimeout=60000
                }.inputStream.use{input->temp.outputStream().use{output->
                    val buf=ByteArray(65536)
                    while(true){val count=input.read(buf);if(count<0)break
                        total+=count;require(total<=200L*1024*1024 && total<=release.getLong("size")){"Update exceeds declared size"}
                        digest.update(buf,0,count);output.write(buf,0,count)
                    }
                }}
                val hex=digest.digest().joinToString(""){"%02x".format(it)}
                require(total==release.getLong("size") && hex==release.getString("sha256")){"Release checksum mismatch"}
                require(temp.renameTo(dest)){"Could not finalize APK download"}
            } finally {temp.delete()}
        } else api.download(release.getString("download_path"),dest,release.getString("sha256"),200L*1024*1024)
        val flags=if(Build.VERSION.SDK_INT>=28)PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES
        val info=context.packageManager.getPackageArchiveInfo(dest.path,flags) ?: error("Invalid APK")
        require(info.packageName==context.packageName){"Update has a different package ID"}
        val version=if(Build.VERSION.SDK_INT>=28)info.longVersionCode else info.versionCode.toLong()
        require(version>BuildConfig.VERSION_CODE){"Update is not newer"}
        val installed=context.packageManager.getPackageInfo(context.packageName,flags)
        val old=(if(Build.VERSION.SDK_INT>=28)
            installed.signingInfo?.signingCertificateHistory ?: installed.signingInfo?.apkContentsSigners
            else installed.signatures)?.map{it.toCharsString()}?.toSet()
        val new=(if(Build.VERSION.SDK_INT>=28)
            info.signingInfo?.signingCertificateHistory ?: info.signingInfo?.apkContentsSigners
            else info.signatures)?.map{it.toCharsString()}?.toSet()
        // Valid signing-key rotation lineages share the original certificate.
        // The OS will do its authoritative APK signature/lineage validation.
        require(!old.isNullOrEmpty() && !new.isNullOrEmpty() && old.intersect(new).isNotEmpty()) {
            "This installed APK uses a different signing certificate. Android cannot update it in place; existing app data has not been touched."
        }
        return dest
    }
    fun install(activity:Activity,file:File) {
        if(!activity.packageManager.canRequestPackageInstalls()) {
            activity.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,Uri.parse("package:"+activity.packageName)))
            android.widget.Toast.makeText(activity,"Allow updates from Anki Companion, then tap Update again",android.widget.Toast.LENGTH_LONG).show();return
        }
        val uri=FileProvider.getUriForFile(activity,activity.packageName+".files",file)
        activity.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri,"application/vnd.android.package-archive").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))
    }
}
