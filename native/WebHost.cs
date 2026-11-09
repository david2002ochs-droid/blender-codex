// Windows x64 .NET Framework host. stdin/stdout protocol is documented in web_host.py.
// A real WS_CHILD window is attached before it becomes visible; no browser window.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

internal sealed class WebHost : Form
{
    [DllImport("user32.dll", SetLastError = true)] private static extern IntPtr SetParent(IntPtr child, IntPtr parent);
    [DllImport("user32.dll")] private static extern IntPtr GetParent(IntPtr child);
    [DllImport("user32.dll")] private static extern bool IsWindow(IntPtr hwnd);
    [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr hwnd);
    [DllImport("user32.dll")] private static extern bool GetWindowRect(IntPtr hwnd, out NativeRect rect);
    [StructLayout(LayoutKind.Sequential)] private struct NativeRect { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
    [DllImport("user32.dll")] private static extern IntPtr GetWindowDpiAwarenessContext(IntPtr hwnd);
    [DllImport("user32.dll")] private static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
    [DllImport("user32.dll")] private static extern bool SetProcessDPIAware();
    [DllImport("user32.dll", SetLastError = true)] private static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x, int y, int cx, int cy, uint flags);

    private readonly IntPtr owner;
    private readonly int ownerPid;
    private readonly Uri startUri;
    private readonly string profile;
    private readonly WebView2 browser;
    private readonly System.Windows.Forms.Timer ownerTimer;
    private bool desiredVisible;
    private bool closing;
    private bool geometrySet;
    private bool resizing;
    private Point gestureStart;
    private Rectangle gestureBounds;
    private int gestureEdge;
    private System.Windows.Forms.Timer dragTimer;
    private static readonly object outputLock = new object();

    private static void Stage(string text)
    {
        Emit(new { type = "diagnostic", stage = text });
    }

    private static void Emit(object data)
    {
        lock (outputLock)
        {
            Console.Out.WriteLine(new JavaScriptSerializer().Serialize(data));
            Console.Out.Flush();
        }
    }

    private WebHost(IntPtr parent, int pid, Uri url, string dataPath)
    {
        Stage("form_constructor");
        owner = parent; ownerPid = pid; startUri = url; profile = dataPath;
        FormBorderStyle = FormBorderStyle.None;
        // Tell WinForms this really is a child control. WS_CHILD alone leaves
        // Form's top-level placement/visibility bookkeeping active.
        TopLevel = false;
        ShowInTaskbar = false;
        StartPosition = FormStartPosition.Manual;
        AutoScaleMode = AutoScaleMode.None;
        BackColor = Color.FromArgb(24, 25, 29);
        Size = new Size(1, 1);
        browser = new WebView2();
        Stage("webview_control_created");
        browser.Dock = DockStyle.Fill;
        browser.DefaultBackgroundColor = BackColor;
        Controls.Add(browser);
        if (!url.Fragment.Contains("surface=markup") && !url.Fragment.Contains("surface=image-editor"))
        {
            for (int edge = 0; edge < 8; edge++)
            {
                int capturedEdge = edge;
                var grip = new Panel { BackColor = Color.FromArgb(238, 240, 244),
                    AccessibleName = "Resize chat " + edge };
                Cursor[] cursors = { Cursors.SizeNWSE, Cursors.SizeNS, Cursors.SizeNESW, Cursors.SizeWE,
                    Cursors.SizeNWSE, Cursors.SizeNS, Cursors.SizeNESW, Cursors.SizeWE };
                grip.Cursor = cursors[edge];
                Controls.Add(grip); grip.BringToFront();
                Action arrange = delegate {
                    int g=6, c=12, w=ClientSize.Width, h=ClientSize.Height;
                    Rectangle[] zones = {new Rectangle(0,0,c,c), new Rectangle(c,0,Math.Max(1,w-2*c),g),
                        new Rectangle(w-c,0,c,c), new Rectangle(w-g,c,g,Math.Max(1,h-2*c)),
                        new Rectangle(w-c,h-c,c,c), new Rectangle(c,h-g,Math.Max(1,w-2*c),g),
                        new Rectangle(0,h-c,c,c), new Rectangle(0,c,g,Math.Max(1,h-2*c))};
                    grip.Bounds=zones[capturedEdge];
                };
                SizeChanged += delegate { arrange(); }; arrange();
                grip.MouseDown += delegate(object sender, MouseEventArgs e) {
                    if (e.Button != MouseButtons.Left) return;
                    BeginGesture(capturedEdge); grip.Capture=true;
                };
                grip.MouseMove += delegate { if(resizing) MoveGesture(false); };
                grip.MouseUp += delegate { if(resizing) MoveGesture(true); grip.Capture=false; };
                grip.MouseCaptureChanged += delegate { if(!grip.Capture && resizing) MoveGesture(true); };
            }
        }
        Stage("webview_control_added");
        ownerTimer = new System.Windows.Forms.Timer();
        ownerTimer.Interval = 500;
        ownerTimer.Tick += delegate
        {
            uint currentPid;
            GetWindowThreadProcessId(owner, out currentPid);
            if (!IsWindow(owner) || currentPid != ownerPid) Close();
            else
            {
                try { if (Process.GetProcessById(ownerPid).HasExited) Close(); }
                catch (ArgumentException) { Close(); }
            }
        };
    }

    [DllImport("user32.dll")] private static extern bool GetClientRect(IntPtr hwnd, out NativeRect rect);

    private void BeginGesture(int edge)
    {
        resizing=true; gestureEdge=edge; gestureStart=Cursor.Position; gestureBounds=Bounds;
    }

    private void MoveGesture(bool finished)
    {
        if(!resizing) return;
        int dx=Cursor.Position.X-gestureStart.X, dy=Cursor.Position.Y-gestureStart.Y;
        int x=gestureBounds.X,y=gestureBounds.Y,w=gestureBounds.Width,h=gestureBounds.Height;
        if(gestureEdge==8) { x+=dx; y+=dy; }
        else {
            if(gestureEdge==0 || gestureEdge==6 || gestureEdge==7) {x+=dx;w-=dx;}
            if(gestureEdge==2 || gestureEdge==3 || gestureEdge==4) w+=dx;
            if(gestureEdge==0 || gestureEdge==1 || gestureEdge==2) {y+=dy;h-=dy;}
            if(gestureEdge==4 || gestureEdge==5 || gestureEdge==6) h+=dy;
        }
        NativeRect parent; GetClientRect(owner,out parent);
        int pw=Math.Max(1,parent.Right-parent.Left),ph=Math.Max(1,parent.Bottom-parent.Top);
        int mw=Math.Min(240,pw),mh=Math.Min(180,ph);
        if(w<mw) {if(gestureEdge==0||gestureEdge==6||gestureEdge==7)x=gestureBounds.Right-mw;w=mw;}
        if(h<mh) {if(gestureEdge==0||gestureEdge==1||gestureEdge==2)y=gestureBounds.Bottom-mh;h=mh;}
        w=Math.Min(w,pw);h=Math.Min(h,ph);x=Math.Max(0,Math.Min(x,pw-w));y=Math.Max(0,Math.Min(y,ph-h));
        Bounds=new Rectangle(x,y,w,h);
        SetWindowPos(Handle,IntPtr.Zero,x,y,w,h,0x0010);
        Emit(new {type="bounds_changed",x=x,y=y,width=w,height=h,final=finished});
        if(finished) {resizing=false;if(dragTimer!=null)dragTimer.Stop();}
    }

    protected override CreateParams CreateParams
    {
        get
        {
            CreateParams cp = base.CreateParams;
            cp.Parent = owner;
            cp.Style = (cp.Style & unchecked((int)~0x80000000)) | 0x40000000 | 0x04000000 | 0x02000000;
            cp.ExStyle &= ~0x00040000; // no WS_EX_APPWINDOW
            return cp;
        }
    }

    protected override bool ShowWithoutActivation { get { return true; } }
    protected override void SetVisibleCore(bool value) { base.SetVisibleCore(value && desiredVisible); }

    protected override void OnSizeChanged(EventArgs e)
    {
        base.OnSizeChanged(e);
        if (Width < 2 || Height < 2) return;
        // Clip the actual child HWND, including WebView2, rather than painting
        // white rounded corners over Blender's changing viewport background.
        float dpi = 96;
        if (IsHandleCreated) using (var graphics = CreateGraphics()) dpi = graphics.DpiX;
        float diameter = Math.Min(Math.Min(Width, Height), 24 * dpi / 96);
        using (var outline = new GraphicsPath())
        {
            outline.AddArc(0, 0, diameter, diameter, 180, 90);
            outline.AddArc(Width - diameter, 0, diameter, diameter, 270, 90);
            outline.AddArc(Width - diameter, Height - diameter, diameter, diameter, 0, 90);
            outline.AddArc(0, Height - diameter, diameter, diameter, 90, 90);
            outline.CloseFigure();
            Region previous = Region;
            Region = new Region(outline);
            if (previous != null) previous.Dispose();
        }
    }

    protected override void OnHandleCreated(EventArgs e)
    {
        Stage("handle_created_enter");
        base.OnHandleCreated(e);
        Stage("set_parent_enter");
        SetParent(Handle, owner);
        Stage("set_parent_complete");
        if (GetParent(Handle) != owner) throw new InvalidOperationException("Could not attach WebView2 to Blender HWND");
        ownerTimer.Start();
        BeginInvoke(new Action(InitializeBrowser));
    }

    private bool Allowed(string uri)
    {
        Uri parsed;
        return Uri.TryCreate(uri, UriKind.Absolute, out parsed) &&
            parsed.Scheme == startUri.Scheme && parsed.Host == startUri.Host &&
            parsed.Port == startUri.Port && String.IsNullOrEmpty(parsed.UserInfo);
    }

    private bool AllowedDownload(string uri)
    {
        // The chat creates Blob URLs only after fetching an authenticated
        // resource. Never turn arbitrary remote links into native downloads.
        return uri != null && uri.StartsWith("blob:", StringComparison.Ordinal) &&
            Allowed(uri.Substring(5));
    }

    private async void InitializeBrowser()
    {
        try
        {
            Stage("environment_initializing");
            Directory.CreateDirectory(profile);
            var environment = await CoreWebView2Environment.CreateAsync(null, profile);
            Stage("environment_ready");
            // Create the WinForms control HWND explicitly. With a hidden owner,
            // EnsureCoreWebView2Async otherwise may wait for first visibility.
            IntPtr browserHandle = browser.Handle;
            await browser.EnsureCoreWebView2Async(environment);
            Stage("core_ready");
            if (closing) return;
            var core = browser.CoreWebView2;
            var settings = core.Settings;
            settings.AreDevToolsEnabled = false;
            settings.AreDefaultContextMenusEnabled = false;
            settings.AreBrowserAcceleratorKeysEnabled = false;
            settings.AreHostObjectsAllowed = false;
            settings.IsWebMessageEnabled = true;
            core.WebMessageReceived += delegate(object sender, CoreWebView2WebMessageReceivedEventArgs args) {
                if(!Allowed(args.Source) || startUri.Fragment.Contains("surface=")) return;
                try {
                    var message=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(args.WebMessageAsJson);
                    if(Convert.ToString(message["type"])!="window_drag" || Convert.ToString(message["phase"])!="start" || Control.MouseButtons!=MouseButtons.Left) return;
                    BeginGesture(8);
                    if(dragTimer==null) {
                        dragTimer=new System.Windows.Forms.Timer();dragTimer.Interval=16;
                        dragTimer.Tick+=delegate { MoveGesture(Control.MouseButtons!=MouseButtons.Left); };
                    }
                    dragTimer.Start();
                } catch { }
            };
            settings.AreDefaultScriptDialogsEnabled = false;
            settings.IsStatusBarEnabled = false;
            settings.IsZoomControlEnabled = false;
            settings.IsGeneralAutofillEnabled = false;
            settings.IsPasswordAutosaveEnabled = false;
            core.NavigationStarting += delegate(object s, CoreWebView2NavigationStartingEventArgs args) { args.Cancel = !Allowed(args.Uri); };
            core.FrameNavigationStarting += delegate(object s, CoreWebView2NavigationStartingEventArgs args) { args.Cancel = !Allowed(args.Uri); };
            core.NewWindowRequested += delegate(object s, CoreWebView2NewWindowRequestedEventArgs args) { args.Handled = true; };
            core.DownloadStarting += delegate(object s, CoreWebView2DownloadStartingEventArgs args)
            {
                args.Cancel = !AllowedDownload(args.DownloadOperation.Uri);
                // Keep WebView2's download UI and collision handling visible.
                // Do not choose an output path or open downloaded files here.
                args.Handled = false;
            };
            core.PermissionRequested += delegate(object s, CoreWebView2PermissionRequestedEventArgs args) { args.State = CoreWebView2PermissionState.Deny; };
            core.AddWebResourceRequestedFilter("*", CoreWebView2WebResourceContext.All);
            core.WebResourceRequested += delegate(object s, CoreWebView2WebResourceRequestedEventArgs args)
            {
                if (!Allowed(args.Request.Uri))
                    args.Response = environment.CreateWebResourceResponse(new MemoryStream(new byte[0]), 403, "Blocked origin", "Content-Type: text/plain");
            };
            core.ProcessFailed += delegate { Fail("WebView2 rendering process failed"); };
            core.NavigationCompleted += delegate(object sender, CoreWebView2NavigationCompletedEventArgs args)
            {
                Emit(new { type = "navigation", success = args.IsSuccess, status = args.WebErrorStatus.ToString() });
            };
            await core.AddScriptToExecuteOnDocumentCreatedAsync(@"document.addEventListener('pointerdown', function(e) {
                if(e.button !== 0 || !e.target.closest('[data-window-drag]') ||
                  e.target.closest('button,a,input,textarea,select,[role=button],[role=tab],[role=menuitem],[contenteditable=true]')) return;
                window.chrome.webview.postMessage({type:'window_drag',phase:'start'});
                e.preventDefault();
            });");
            core.Navigate(startUri.AbsoluteUri);
            Emit(new { type = "ready", hwnd = Handle.ToInt64(), parent_hwnd = owner.ToInt64() });
        }
        catch (Exception exception)
        {
            // Avoid echoing the token-bearing URL or other arguments into logs.
            Fail("WebView2 initialization failed: " + exception.GetType().Name + " (check installed WebView2 Runtime)");
        }
    }

    private void Fail(string text)
    {
        Emit(new { type = "error", text = text });
        Environment.ExitCode = 1;
        Close();
    }

    private void ReportVisibility()
    {
        NativeRect rect;
        GetWindowRect(Handle, out rect);
        Emit(new { type = "visibility", visible = Visible,
            native_visible = IsWindowVisible(Handle),
            left = rect.Left, top = rect.Top, width = rect.Right - rect.Left, height = rect.Bottom - rect.Top,
            browser_visible = browser.Visible, browser_width = browser.Width, browser_height = browser.Height,
            hwnd = Handle.ToInt64(), parent_hwnd = GetParent(Handle).ToInt64() });
    }

    private void Apply(string line)
    {
        if (closing) return;
        try
        {
            var data = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(line);
            var command = Convert.ToString(data["type"]);
            if (command == "close") { Close(); return; }
            if (command == "hide") { desiredVisible = false; Hide(); ReportVisibility(); return; }
            if (command == "show") { if (geometrySet) { desiredVisible = true; Show(); } ReportVisibility(); return; }
            if (command != "geometry") throw new ArgumentException();
            if(resizing) return; // Native gesture owns placement until pointer release.
            int x = Convert.ToInt32(data["x"]), y = Convert.ToInt32(data["y"]);
            int width = Convert.ToInt32(data["width"]), height = Convert.ToInt32(data["height"]);
            if (width <= 0 || height <= 0 || width > 32768 || height > 32768) throw new ArgumentException();
            // WinForms sees physical pixels because our UI thread matches Blender's DPI context.
            geometrySet = true;
            desiredVisible = true;
            Bounds = new Rectangle(x, y, width, height);
            Show();
            browser.Visible = true;
            browser.PerformLayout();
            // Apply native placement last: Form.Show must not overwrite it.
            if (!SetWindowPos(Handle, IntPtr.Zero, x, y, width, height, 0x0010 | 0x0040))
                throw new InvalidOperationException(); // no activate, show
            browser.Invalidate();
            Emit(new { type = "geometry", x = x, y = y, width = width, height = height,
                hwnd = Handle.ToInt64(), parent_hwnd = GetParent(Handle).ToInt64(), visible = Visible });
            ReportVisibility();
        }
        catch { Fail("Invalid WebView2 control command"); }
    }

    internal void ReadCommands()
    {
        try
        {
            string line;
            while ((line = Console.In.ReadLine()) != null)
            {
                if (line.Length > 4096) break;
                string captured = line;
                if (IsDisposed) return;
                BeginInvoke(new Action(delegate { Apply(captured); }));
            }
        }
        catch (Exception) { }
        try { if (!IsDisposed) BeginInvoke(new Action(Close)); }
        catch (InvalidOperationException) { }
    }

    protected override void OnFormClosed(FormClosedEventArgs e)
    {
        closing = true;
        if(dragTimer!=null) {dragTimer.Stop();dragTimer.Dispose();}
        ownerTimer.Stop();
        ownerTimer.Dispose();
        browser.Dispose();
        base.OnFormClosed(e);
    }

    [STAThread]
    private static int Main(string[] args)
    {
        Console.InputEncoding = Encoding.UTF8;
        Console.OutputEncoding = new UTF8Encoding(false);
        try
        {
            if (args.Length != 4) throw new ArgumentException();
            Stage("process_started");
            IntPtr parent = new IntPtr(Int64.Parse(args[0]));
            int pid = Int32.Parse(args[1]);
            uint actualPid;
            GetWindowThreadProcessId(parent, out actualPid);
            if (!IsWindow(parent) || actualPid != pid) throw new ArgumentException();
            Uri url = new Uri(args[2]);
            if (url.Scheme != "http" || !(url.Host == "127.0.0.1" || url.Host == "localhost" || url.Host == "[::1]") || !String.IsNullOrEmpty(url.UserInfo))
                throw new ArgumentException();
            try { SetThreadDpiAwarenessContext(GetWindowDpiAwarenessContext(parent)); }
            catch (EntryPointNotFoundException) { SetProcessDPIAware(); }
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Stage("creating_form");
            using (var host = new WebHost(parent, pid, url, args[3]))
            {
                Stage("creating_handle");
                IntPtr created = host.Handle;
                Stage("handle_ready");
                var input = new Thread(host.ReadCommands);
                input.IsBackground = true;
                input.Start();
                Stage("message_loop_starting");
                Application.Run(host);
            }
            return Environment.ExitCode;
        }
        catch (Exception exception)
        {
            Emit(new { type = "error", text = "WebView2 host failed: " + exception.GetType().Name });
            return 1;
        }
    }
}
