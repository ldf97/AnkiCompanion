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
        val result=api.json("/v1/updates/android?current="+BuildConfig.VERSION_NAME+"&build="+BuildConfig.VERSION_CODE)
        result.put("checked_ms",System.currentTimeMillis());store.save("update.json",result);store.setSetting("update_error","")
        if(result.optBoolean("available"))notify(context,result)
        return result
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
        api.download(release.getString("download_path"),dest,release.getString("sha256"),200L*1024*1024)
        val flags=if(Build.VERSION.SDK_INT>=28)PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES
        val info=context.packageManager.getPackageArchiveInfo(dest.path,flags) ?: error("Invalid APK")
        require(info.packageName==context.packageName){"Update has a different package ID"}
        val version=if(Build.VERSION.SDK_INT>=28)info.longVersionCode else info.versionCode.toLong()
        require(version>BuildConfig.VERSION_CODE){"Update is not newer"}
        val installed=context.packageManager.getPackageInfo(context.packageName,flags)
        val old=(if(Build.VERSION.SDK_INT>=28)installed.signingInfo?.apkContentsSigners else installed.signatures)?.map{it.toCharsString()}?.toSet()
        val new=(if(Build.VERSION.SDK_INT>=28)info.signingInfo?.apkContentsSigners else info.signatures)?.map{it.toCharsString()}?.toSet()
        require(!old.isNullOrEmpty() && old==new){"APK signing key does not match this installation"}
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
