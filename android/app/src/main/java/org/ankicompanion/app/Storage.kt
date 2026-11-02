package org.ankicompanion.app

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import android.util.AtomicFile
import org.json.JSONObject
import java.io.File
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import java.util.UUID

class Storage(val context:Context) {
    private val prefs=context.getSharedPreferences("companion",Context.MODE_PRIVATE)
    val root=context.filesDir
    val deviceId:String get() {
        var id=prefs.getString("device_id",null)
        if(id==null){id="android-"+UUID.randomUUID().toString();check(prefs.edit().putString("device_id",id).commit()){"Could not save stable device ID"}}
        return id
    }
    private fun key():SecretKey {
        val store=KeyStore.getInstance("AndroidKeyStore");store.load(null)
        (store.getKey("connection",null) as? SecretKey)?.let{return it}
        val generator=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore")
        generator.init(KeyGenParameterSpec.Builder("connection",KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
        return generator.generateKey()
    }
    fun connection():JSONObject? {
        val encoded=prefs.getString("connection",null) ?: return null
        return try {
            val data=Base64.decode(encoded,Base64.NO_WRAP);val cipher=Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE,key(),GCMParameterSpec(128,data.copyOfRange(0,12)))
            JSONObject(String(cipher.doFinal(data.copyOfRange(12,data.size)),Charsets.UTF_8))
        } catch(e:Exception){null}
    }
    fun saveConnection(value:JSONObject) {
        val cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.ENCRYPT_MODE,key())
        val encrypted=cipher.iv+cipher.doFinal(value.toString().toByteArray(Charsets.UTF_8))
        check(prefs.edit().putString("connection",Base64.encodeToString(encrypted,Base64.NO_WRAP)).commit()){"Could not save encrypted connection"}
    }
    // Android AtomicFile rolls back a torn write if an APK update or app
    // shutdown interrupts a JSON replacement. Normal updates reuse filesDir.
    fun load(name:String):JSONObject? = try {
        val file=AtomicFile(File(root,name))
        JSONObject(String(file.openRead().use{it.readBytes()},Charsets.UTF_8))
    } catch(e:Exception){null}
    @Synchronized fun save(name:String,value:JSONObject) {
        val file=AtomicFile(File(root,name))
        val stream=file.startWrite()
        try {
            stream.write(value.toString().toByteArray(Charsets.UTF_8))
            file.finishWrite(stream)
        } catch(e:Exception) {
            file.failWrite(stream)
            throw e
        }
    }
    fun getSetting(name:String,default:String=""):String=prefs.getString(name,default) ?: default
    fun setSetting(name:String,value:String){
        check(prefs.edit().putString(name,value).commit()){"Could not save $name"}
    }
}
