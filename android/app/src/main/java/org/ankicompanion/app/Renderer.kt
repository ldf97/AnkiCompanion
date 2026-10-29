package org.ankicompanion.app

import android.content.Context
import android.graphics.*
import android.view.View
import com.caverock.androidsvg.SVG
import org.json.JSONObject
import java.io.File
import java.time.Instant
import java.time.ZoneId
import kotlin.math.pow
import kotlin.math.cos

data class Frame(val image:Bitmap,val badge:Bitmap,val warning:Boolean)

class Renderer(private val context:Context) {
    private val regular=Typeface.createFromAsset(context.assets,"DejaVuSans.ttf")
    private val bold=Typeface.createFromAsset(context.assets,"DejaVuSans-Bold.ttf")
    private fun cover(canvas:Canvas,file:File,target:RectF) {
        val opts=BitmapFactory.Options().apply{inJustDecodeBounds=true};BitmapFactory.decodeFile(file.path,opts)
        var sample=1
        while(opts.outWidth/(sample*2)>=target.width() && opts.outHeight/(sample*2)>=target.height())sample*=2
        val image=BitmapFactory.decodeFile(file.path,BitmapFactory.Options().apply{inSampleSize=sample}) ?: error("Image missing")
        val ratio=maxOf(target.width()/image.width,target.height()/image.height)
        val width=target.width()/ratio;val height=target.height()/ratio
        val source=Rect(((image.width-width)/2).toInt(),((image.height-height)/2).toInt(),((image.width+width)/2).toInt(),((image.height+height)/2).toInt())
        canvas.drawBitmap(image,source,target,Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG));image.recycle()
    }
    private fun icon(root:File,path:String,w:Int,h:Int):Bitmap {
        val bitmap=Bitmap.createBitmap(w,h,Bitmap.Config.ARGB_8888)
        if(path.endsWith(".svg"))File(root,path).inputStream().use {SVG.getFromInputStream(it).renderToCanvas(Canvas(bitmap),RectF(0f,0f,w.toFloat(),h.toFloat()))}
        else cover(Canvas(bitmap),File(root,path),RectF(0f,0f,w.toFloat(),h.toFloat()))
        return bitmap
    }
    fun draw(state:JSONObject,root:File,withBadge:Boolean=false,now:Long=System.currentTimeMillis()):Frame {
        val skin=JSONObject(File(root,"skin.json").readText());val settings=state.getJSONObject("settings")
        val day=Rules.day(now,settings.getString("timezone"),settings.getInt("rollover_minute"))
        val original=state.getJSONObject("lineup");val sameDay=day==original.getString("date")
        val lineup=if(sameDay)original else Rules.lineup(day,skin,state.getString("seed"))
        val completed=(sameDay || state.optString("local_day")==day) && state.getBoolean("completed");val local=Instant.ofEpochMilli(now).atZone(ZoneId.of(settings.getString("timezone")))
        val minute=local.hour*60+local.minute;val slot=Rules.slot(skin,minute,completed)
        val record=lineup.getJSONObject("records").getJSONObject(slot.getString("id"));val style=skin.getJSONObject("style")
        val result=Bitmap.createBitmap(1100,468,Bitmap.Config.ARGB_8888);val canvas=Canvas(result);val paint=Paint(Paint.ANTI_ALIAS_FLAG)
        cover(canvas,File(root,if(completed)record.getString("portrait") else record.getString("background")),RectF(0f,0f,1100f,468f))
        if(slot.optBoolean("tint")) {
            val alpha=(Rules.tint(skin,minute,completed)*255).toInt();val rgb=style.getJSONArray("red_tint_rgb")
            canvas.drawColor(Color.argb(alpha,rgb.getInt(0),rgb.getInt(1),rgb.getInt(2)))
        }
        for(x in 0 until 1100){paint.color=Color.argb((212*(1-x/1100.0).pow(1.5)).toInt(),4,5,7);canvas.drawRect(x.toFloat(),0f,x+1f,468f,paint)}
        if(!completed) {
            val box=RectF(728f,70f,1058f,400f);val clip=Path().apply{addRoundRect(box,22f,22f,Path.Direction.CW)}
            canvas.save();canvas.clipPath(clip);cover(canvas,File(root,record.getString("portrait")),box);canvas.restore()
            paint.style=Paint.Style.STROKE;paint.strokeWidth=3f;paint.color=Color.rgb(244,220,183);canvas.drawRoundRect(box,22f,22f,paint);paint.style=Paint.Style.FILL
        }
        val icons=style.getJSONObject("icons");val flame=icon(root,icons.getString(if(completed)"flame_lit" else "flame_unlit"),67,75)
        canvas.drawBitmap(flame,41f,52f,null);flame.recycle()
        fun text(value:String,x:Float,y:Float,size:Float,face:Typeface,color:Int,stroke:Boolean=false) {
            paint.typeface=face;paint.textSize=size;paint.style=Paint.Style.FILL
            val baseline=y-paint.fontMetrics.top
            if(stroke){paint.style=Paint.Style.STROKE;paint.strokeWidth=2f;paint.color=Color.rgb(2,3,5);canvas.drawText(value,x,baseline,paint);paint.style=Paint.Style.FILL}
            paint.color=color;canvas.drawText(value,x,baseline,paint)
        }
        text(state.getInt("streak").toString(),128f,64f,76f,bold,Color.rgb(255,240,218))
        text(style.getString("streak_label"),134f,157f,24f,regular,Color.rgb(255,227,204))
        var lines=listOf<String>();var size=25f
        for(candidate in listOf(39f,36f,33f,30f,27f,25f)) {
            paint.typeface=bold;paint.textSize=candidate;val output=mutableListOf<String>();var current=""
            for(word in record.getString("quote").split(Regex("\\s+"))) {
                val next=(current+" "+word).trim()
                if(paint.measureText(next)<=if(completed)660f else 620f)current=next else {if(current.isNotEmpty())output.add(current);current=word}
            };if(current.isNotEmpty())output.add(current);lines=output;size=candidate;if(lines.size<=3)break
        }
        lines.forEachIndexed {i,line->text(line,52f,255f+i*(size+15),size,bold,Color.WHITE,true)}
        val badge=icon(root,icons.getString("warning_badge"),58,58);val warning=!completed && minute>=style.getInt("warning_start_minute")
        if(warning && withBadge)canvas.drawBitmap(badge,95f,35f,null)
        return Frame(result,badge,warning)
    }
}

class SceneView(context:Context):View(context) {
    var frame:Frame?=null
        set(value){val old=field;field=value;if(old!==value){old?.image?.recycle();old?.badge?.recycle()};invalidate()}
    override fun onMeasure(w:Int,h:Int){val width=MeasureSpec.getSize(w);setMeasuredDimension(width,(width*468f/1100).toInt())}
    override fun onDraw(canvas:Canvas) {
        super.onDraw(canvas);val f=frame ?: return
        val scale=width/1100f;canvas.save();canvas.scale(scale,scale);canvas.drawBitmap(f.image,0f,0f,Paint(Paint.FILTER_BITMAP_FLAG))
        if(f.warning) {
            val pulse=1+.125*(1-cos(android.os.SystemClock.uptimeMillis()*2*Math.PI/1800));val side=(58*pulse).toFloat()
            canvas.drawBitmap(f.badge,null,RectF(124-side/2,64-side/2,124+side/2,64+side/2),Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG))
            postInvalidateDelayed(60)
        };canvas.restore()
    }
}
