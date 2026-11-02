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
    fun checkAnkiDroid(context:Context,force:Boolean=false):JSONObject? {
        val store=Storage(context)
        val cached=store.load("ankidroid-update.json")
        if(!force && cached!=null && System.currentTimeMillis()-cached.optLong("checked_ms")<60*60*1000)return cached
        val result=try{githubRelease("ankidroid",context)}catch(e:java.io.FileNotFoundException){
            JSONObject().put("configured",true).put("available",false)
                .put("message","No production-signed AnkiDroid Companion update has been published")
        }
        result.put("checked_ms",System.currentTimeMillis())
        store.save("ankidroid-update.json",result)
        if(result.optBoolean("available"))notify(context,result)
        return result
    }
    private fun installedVersion(context:Context,packageName:String):Long {
        return try {
            val info=context.packageManager.getPackageInfo(packageName,0)
            if(Build.VERSION.SDK_INT>=28)info.longVersionCode else info.versionCode.toLong()
        } catch(e:PackageManager.NameNotFoundException){0L}
    }
    fun signingFingerprint(context:Context,packageName:String):String {
        return try {
            val flags=if(Build.VERSION.SDK_INT>=28)PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES
            val info=context.packageManager.getPackageInfo(packageName,flags)
            val signatures=(if(Build.VERSION.SDK_INT>=28)info.signingInfo?.apkContentsSigners else info.signatures)
                ?: return "Not available"
            signatures.joinToString(", ") { certificate ->
                java.security.MessageDigest.getInstance("SHA-256").digest(certificate.toByteArray())
                    .joinToString(""){"%02x".format(it)}
            }
        } catch(e:PackageManager.NameNotFoundException){"Not installed"}
    }
    private fun githubRelease(platform:String="android",context:Context?=null):JSONObject {
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
        require(platform=="android" || platform=="ankidroid"){"Unsupported update platform"}
        if(!manifest.getJSONObject("assets").has(platform))return JSONObject()
            .put("configured",true).put("available",false)
            .put("message","Android signed update not yet published")
        val asset=manifest.getJSONObject("assets").getJSONObject(platform)
        val name=asset.getString("filename")
        require(Regex("[A-Za-z0-9_.-]+\\.apk").matches(name)){"Invalid release APK name"}
        require(Regex("[0-9a-f]{64}").matches(asset.getString("sha256"))){"Invalid release checksum"}
        val size=asset.getLong("size")
        require(size in 1..(200L*1024*1024)){"Invalid release size"}
        val target=if(platform=="android")"org.ankicompanion.app" else "com.ichi2.anki.companion"
        val targetCode=asset.optLong("version_code",build.toLong())
        val current=if(context!=null)installedVersion(context,target) else BuildConfig.VERSION_CODE.toLong()
        val available=targetCode>current
        return JSONObject().put("configured",true).put("available",available)
            .put("platform",platform).put("target_package",target).put("version_code",targetCode)
            .put("version",version).put("build",build).put("filename",name)
            .put("size",size).put("sha256",asset.getString("sha256"))
            .put("download_url","https://github.com/ldf97/AnkiCompanion/releases/latest/download/"+name)
            .put("message",if(available)"Update available" else "Up to date")
    }
    private fun notify(context:Context,result:JSONObject) {
        if(Build.VERSION.SDK_INT>=33 && context.checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)return
        val manager=context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel("updates","App updates",NotificationManager.IMPORTANCE_DEFAULT))
        val ankidroid=result.optString("platform")=="ankidroid"
        val notificationId=if(ankidroid)31 else 30
        val intent=PendingIntent.getActivity(context,notificationId,Intent(context,MainActivity::class.java)
            .putExtra(if(ankidroid)"ankidroid_updates" else "updates",true),PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val notice=android.app.Notification.Builder(context,"updates").setSmallIcon(R.drawable.app_icon)
            .setContentTitle(if(ankidroid)"AnkiDroid Companion update available" else "Anki Companion update available")
            .setContentText("Version "+result.optString("version")+" · tap to update").setContentIntent(intent).setAutoCancel(true).build()
        manager.notify(notificationId,notice)
    }
    fun download(context:Context,api:Api,release:JSONObject):File {
        require(release.getBoolean("available")){"No update available"}
        val target=release.optString("target_package",context.packageName)
        require(target==context.packageName || target=="com.ichi2.anki.companion"){"Unknown update package"}
        val dest=File(context.filesDir,if(target==context.packageName)"updates/companion-update.apk" else "updates/ankidroid-companion-update.apk")
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
        require(info.packageName==target){"Update has a different package ID"}
        val version=if(Build.VERSION.SDK_INT>=28)info.longVersionCode else info.versionCode.toLong()
        require(version>installedVersion(context,target)){"Update is not newer"}
        val installed=try{context.packageManager.getPackageInfo(target,flags)}
            catch(e:PackageManager.NameNotFoundException){null}
        val old=(if(Build.VERSION.SDK_INT>=28)
            installed?.signingInfo?.signingCertificateHistory ?: installed?.signingInfo?.apkContentsSigners
            else installed?.signatures)?.map{it.toCharsString()}?.toSet()
        val new=(if(Build.VERSION.SDK_INT>=28)
            info.signingInfo?.signingCertificateHistory ?: info.signingInfo?.apkContentsSigners
            else info.signatures)?.map{it.toCharsString()}?.toSet()
        // Valid signing-key rotation lineages share the original certificate.
        // The OS will do its authoritative APK signature/lineage validation.
        // Installing a missing companion is permitted. Updating an installed
        // package requires the SAME signer, or a valid Android signing lineage.
        // A public update can never bypass this platform security requirement.
        require(!new.isNullOrEmpty()){"Release has no readable signing certificate"}
        if(installed!=null)require(!old.isNullOrEmpty() && old.intersect(new).isNotEmpty()) {
            "The installed Android app uses an incompatible signing certificate. The update was stopped BEFORE touching existing data. A compatible key or guided data migration is required."
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
