package org.ankicompanion.app

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
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
        if(id==null){id="android-"+UUID.randomUUID().toString();prefs.edit().putString("device_id",id).apply()}
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
        prefs.edit().putString("connection",Base64.encodeToString(encrypted,Base64.NO_WRAP)).apply()
    }
    fun load(name:String):JSONObject? = try{JSONObject(File(root,name).readText())}catch(e:Exception){null}
    @Synchronized fun save(name:String,value:JSONObject) {
        val dest=File(root,name);val temp=File(root,"$name.tmp");temp.writeText(value.toString())
        check(temp.renameTo(dest)){"Cannot save $name"}
    }
    fun getSetting(name:String,default:String=""):String=prefs.getString(name,default) ?: default
    fun setSetting(name:String,value:String){prefs.edit().putString(name,value).apply()}
}
