// Hidden parent + real compiled helper: no user window or cursor interaction.
using System;using System.Diagnostics;using System.Drawing;using System.Runtime.InteropServices;
using System.Threading;using System.Collections.Concurrent;using System.Web.Script.Serialization;using System.Collections.Generic;using System.Windows.Forms;
class NativeFloatingTest {
 [StructLayout(LayoutKind.Sequential)]struct Rect{public int L,T,R,B;}
 [DllImport("user32.dll")]static extern IntPtr GetParent(IntPtr h);
 [DllImport("user32.dll")]static extern bool GetWindowRect(IntPtr h,out Rect r);
 [DllImport("user32.dll")]static extern int MapWindowPoints(IntPtr a,IntPtr b,ref Rect r,int n);
 [STAThread]static int Main(string[] args){
  var lines=new ConcurrentQueue<string>();var json=new JavaScriptSerializer();
  using(var parent=new Form()){parent.ClientSize=new Size(1000,800);IntPtr hwnd=parent.Handle;
   var info=new ProcessStartInfo(args[0],hwnd.ToInt64()+" "+Process.GetCurrentProcess().Id+" http://127.0.0.1:12345/ \""+args[1]+"\"");
   info.UseShellExecute=false;info.CreateNoWindow=true;info.RedirectStandardInput=true;info.RedirectStandardOutput=true;
   using(var child=Process.Start(info)){
    child.OutputDataReceived+=(s,e)=>{if(e.Data!=null)lines.Enqueue(e.Data);};child.BeginOutputReadLine();
    Func<string,Dictionary<string,object>> wait=kind=>{var until=DateTime.UtcNow.AddSeconds(40);while(DateTime.UtcNow<until){Application.DoEvents();string line;while(lines.TryDequeue(out line)){var m=json.Deserialize<Dictionary<string,object>>(line);if((string)m["type"]=="error")throw new Exception(line);if((string)m["type"]==kind)return m;}Thread.Sleep(20);}throw new Exception("timeout "+kind);};
    try {var ready=wait("ready");var actual=new IntPtr(Convert.ToInt64(ready["hwnd"]));if(GetParent(actual)!=hwnd)throw new Exception("not embedded");
     int[,] samples={{20,30,300,400},{110,85,550,250},{3,4,240,180},{40,45,800,600}};
     for(int i=0;i<4;i++){child.StandardInput.WriteLine(json.Serialize(new{type="geometry",x=samples[i,0],y=samples[i,1],width=samples[i,2],height=samples[i,3]}));child.StandardInput.Flush();wait("geometry");Rect r;GetWindowRect(actual,out r);MapWindowPoints(IntPtr.Zero,hwnd,ref r,2);if(r.L!=samples[i,0]||r.T!=samples[i,1]||r.R-r.L!=samples[i,2]||r.B-r.T!=samples[i,3])throw new Exception("geometry mismatch");}
     child.StandardInput.WriteLine("{\"type\":\"hide\"}");child.StandardInput.Flush();wait("visibility");
     Console.WriteLine("NATIVE_FLOATING_GEOMETRY_PASS: real child HWND, four XY/width/height samples; hidden parent, no cursor/user Blender interaction");
    } finally {child.StandardInput.WriteLine("{\"type\":\"close\"}");child.StandardInput.Close();if(!child.WaitForExit(5000))child.Kill();}
   }
  }return 0;
 }
}
