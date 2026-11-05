using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Security.Cryptography;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

// Stand-alone forever: never installed inside the AnkiCompanion app folder.
static class Program {
    [STAThread] static void Main() {
        ServicePointManager.SecurityProtocol=(SecurityProtocolType)3072;
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new RecoveryWindow());
    }
}
sealed class RecoveryWindow : Form {
    const string Base="https://github.com/ldf97/AnkiCompanion/releases/latest/download/";
    readonly Button repair=new Button();
    readonly Label status=new Label();
    readonly ProgressBar progress=new ProgressBar();
    public RecoveryWindow() {
        Text="AnkiCompanion Recovery";Size=new Size(530,280);
        MinimumSize=Size;MaximumSize=Size;
        StartPosition=FormStartPosition.CenterScreen;
        FormBorderStyle=FormBorderStyle.FixedDialog;MaximizeBox=false;
        BackColor=Color.FromArgb(20,26,38);ForeColor=Color.White;
        Font=new Font("Segoe UI",10);
        var description=new Label(){Location=new Point(18,18),Size=new Size(480,84),
          Text="AnkiCompanion Recovery\nIndependent repair — works even when AnkiCompanion cannot start.\nChecks GitHub and opens a verified installer without deleting your data."};
        Controls.Add(description);
        repair.Location=new Point(18,108);repair.Size=new Size(480,42);
        repair.Text="Repair / reinstall latest AnkiCompanion";
        repair.BackColor=Color.FromArgb(159,239,219);repair.ForeColor=Color.Black;
        repair.FlatStyle=FlatStyle.Flat;
        repair.Click+=OnRepair;Controls.Add(repair);
        progress.Location=new Point(18,165);progress.Size=new Size(480,14);
        progress.Minimum=0;progress.Maximum=100;Controls.Add(progress);
        status.Location=new Point(18,185);status.Size=new Size(480,56);
        status.Text="Ready — recovery is independent of the main app.";
        Controls.Add(status);
    }
    void SetState(string value,int pct){
        if(IsDisposed||!IsHandleCreated)return;
        BeginInvoke((MethodInvoker)delegate {
            if(IsDisposed)return;
            status.Text=value;progress.Value=Math.Max(0,Math.Min(100,pct));
        });
    }
    void OnRepair(object sender,EventArgs e){
        repair.Enabled=false;
        ThreadPool.QueueUserWorkItem(delegate {
            try {
                SetState("Checking GitHub stable release…",0);
                string json;
                using(var client=new WebClient()){
                    client.Headers[HttpRequestHeader.UserAgent]="AnkiCompanion-Recovery/1.0";
                    json=client.DownloadString(Base+"update.json");
                }
                if(json.Length>128*1024)throw new Exception("Release manifest exceeds size limit");
                var doc=new JavaScriptSerializer().DeserializeObject(json) as Dictionary<string,object>;
                if(doc==null||Convert.ToInt32(doc["schema_version"])!=1)throw new Exception("Invalid release manifest");
                var assets=doc["assets"] as Dictionary<string,object>;
                if(assets==null)throw new Exception("Missing release assets");
                var win=assets["windows"] as Dictionary<string,object>;
                if(win==null)throw new Exception("Windows installer unavailable");
                string filename=Convert.ToString(win["filename"]);
                string checksum=Convert.ToString(win["sha256"]).ToLowerInvariant();
                long size=Convert.ToInt64(win["size"]);
                if(filename!="AnkiCompanion-Windows-Setup.exe" ||
                   !Regex.IsMatch(checksum,"^[a-f0-9]{64}$") ||
                   size<1000000 || size>1024L*1024L*1024L)
                    throw new Exception("Invalid published installer metadata");
                string dir=Path.Combine(Path.GetTempPath(),"AnkiCompanion-Recovery-"+Guid.NewGuid().ToString("N"));
                Directory.CreateDirectory(dir);
                string file=Path.Combine(dir,filename);
                var request=(HttpWebRequest)WebRequest.Create(Base+filename);
                request.UserAgent="AnkiCompanion-Recovery/1.0";
                request.Timeout=30000;request.ReadWriteTimeout=60000;request.AllowAutoRedirect=true;
                SetState("Downloading verified installer…",1);
                long total=0;
                using(var response=(HttpWebResponse)request.GetResponse())
                using(var input=response.GetResponseStream())
                using(var output=File.Create(file)) {
                    var buffer=new byte[65536];int n;int last=0;
                    while((n=input.Read(buffer,0,buffer.Length))>0) {
                        total+=n;
                        if(total>size)throw new Exception("Installer exceeded declared size");
                        output.Write(buffer,0,n);
                        int pct=(int)(total*100/size);
                        if(pct>last){last=pct;SetState("Downloading installer… "+pct+"%",pct);}
                    }
                }
                if(total!=size)throw new Exception("Incomplete installer download");
                SetState("Verifying SHA-256 checksum…",100);
                string actual;
                using(var sha=SHA256.Create())
                using(var stream=File.OpenRead(file))
                    actual=BitConverter.ToString(sha.ComputeHash(stream)).Replace("-","").ToLowerInvariant();
                if(actual!=checksum)throw new Exception("Release checksum mismatch; installation stopped");
                Process.Start(new ProcessStartInfo(file){UseShellExecute=true});
                SetState("Installer launched — approve the Windows installation.",100);
            } catch(Exception ex){
                SetState("Recovery stopped: "+ex.Message,0);
                if(!IsDisposed&&IsHandleCreated)BeginInvoke((MethodInvoker)delegate{
                    MessageBox.Show(this,ex.Message,"Recovery stopped",MessageBoxButtons.OK,MessageBoxIcon.Warning);
                });
            } finally {
                if(!IsDisposed&&IsHandleCreated)BeginInvoke((MethodInvoker)delegate{repair.Enabled=true;});
            }
        });
    }
}
