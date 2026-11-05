package com.ankicompanion.ponglab

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Typeface
import android.media.MediaPlayer
import android.view.MotionEvent
import android.view.View
import kotlin.random.Random

/** Standalone Pong hard mode; loss sound is bundled in the APK. */
class PongView(context: Context): View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val deathSound: MediaPlayer? = MediaPlayer.create(context, R.raw.death_sound)
    private val w = 640f
    private val h = 420f
    private val playerHalfWidth = 50f
    private val aiHalfWidth = 55f
    private val aiSpeed = 7f // Exactly double v1.0.0's 3.5f tracking speed.
    private var ballX = w/2
    private var ballY = h/2
    private var speedX = 5.0f
    private var speedY = 4.5f
    private var paddle = w/2
    private var ai = w/2
    private var playerPoints = 0
    private var aiPoints = 0
    private var ended = false
    private var lost = false
    init { setBackgroundColor(Color.rgb(13,24,46)) }

    private fun resetBall(){
        ballX=w/2; ballY=h/2
        speedX=if(Random.nextBoolean())5f else -5f
        speedY=if(Random.nextBoolean())4.5f else -4.5f
    }

    fun restart() {
        deathSound?.let { if(it.isPlaying)it.pause(); it.seekTo(0) }
        playerPoints=0;aiPoints=0;ended=false;lost=false;resetBall();invalidate()
    }

    override fun onDraw(canvas: Canvas){
        super.onDraw(canvas)
        val sx=width/w; val sy=height/h
        canvas.save(); canvas.scale(sx,sy)
        paint.color=Color.rgb(27,50,87);paint.strokeWidth=2f
        canvas.drawLine(0f,h/2,w,h/2,paint)
        paint.color=Color.rgb(224,233,255);paint.textSize=38f;paint.textAlign=Paint.Align.CENTER
        paint.typeface=Typeface.DEFAULT_BOLD
        canvas.drawText("$aiPoints  :  $playerPoints",w/2,206f,paint)
        val top=ai.coerceIn(aiHalfWidth,w-aiHalfWidth)
        val bottom=paddle.coerceIn(playerHalfWidth,w-playerHalfWidth)
        paint.color=Color.rgb(255,172,119)
        canvas.drawRoundRect(top-aiHalfWidth,30f,top+aiHalfWidth,43f,5f,5f,paint)
        paint.color=Color.rgb(154,242,221)
        canvas.drawRoundRect(bottom-playerHalfWidth,h-45f,bottom+playerHalfWidth,h-32f,5f,5f,paint)
        if(!ended){
            ballX+=speedX;ballY+=speedY
            if(ballX<=9f || ballX>=w-9f) speedX=-speedX
            ai=(ai+(ballX-ai).coerceIn(-aiSpeed,aiSpeed)).coerceIn(aiHalfWidth,w-aiHalfWidth)
            if(ballY<52f && speedY<0 && ballX in (top-aiHalfWidth-8f)..(top+aiHalfWidth+8f)) {
                speedY=-speedY;speedX+=(ballX-top)/32f
            }
            if(ballY>h-54f && speedY>0 && ballX in (bottom-playerHalfWidth-8f)..(bottom+playerHalfWidth+8f)) {
                speedY=-speedY;speedX+=(ballX-bottom)/28f
            }
            speedX=speedX.coerceIn(-8.5f,8.5f)
            if(ballY<0f){playerPoints++;resetBall()}
            if(ballY>h){aiPoints++;resetBall()}
            if(playerPoints>=7 || aiPoints>=7) {
                ended=true
                lost=aiPoints>=7
                if(lost){
                    deathSound?.seekTo(0)
                    deathSound?.start()
                }
            }
        }
        paint.color=Color.WHITE
        canvas.drawCircle(ballX,ballY,8f,paint)
        if(ended){
            paint.color=Color.argb(222,0,0,0)
            canvas.drawRect(0f,0f,w,h,paint)
            paint.textAlign=Paint.Align.CENTER
            paint.typeface=Typeface.create("serif",Typeface.BOLD)
            paint.textSize=76f
            paint.color=if(lost)Color.rgb(184,24,36) else Color.rgb(154,242,221)
            canvas.drawText(if(lost)"YOU DIED" else "YOU WIN",w/2,h/2+6f,paint)
            paint.typeface=Typeface.DEFAULT
            paint.textSize=21f
            paint.color=Color.rgb(240,234,238)
            canvas.drawText("TAP TO CONTINUE",w/2,h/2+59f,paint)
        }
        canvas.restore()
        if(!ended)postInvalidateDelayed(16)
    }

    override fun onTouchEvent(event:MotionEvent):Boolean {
        if(event.actionMasked==MotionEvent.ACTION_DOWN && ended){
            restart()
            return true
        }
        if(!ended && (event.actionMasked==MotionEvent.ACTION_DOWN || event.actionMasked==MotionEvent.ACTION_MOVE)){
            paddle=((event.x/width)*w).coerceIn(playerHalfWidth,w-playerHalfWidth)
            invalidate()
        }
        return true
    }

    override fun onDetachedFromWindow(){
        deathSound?.release()
        super.onDetachedFromWindow()
    }
}
