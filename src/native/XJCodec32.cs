// XJCodec32 —— 32 位原生加解密宿主（替代 PowerShell）
//
// 为什么需要它：游戏的 TP.dll / Socket.dll 是 32 位库，64 位 Python 无法直接加载。
// 这个宿主由系统自带的 C# 编译器（.NET Framework 的 csc.exe）编译成 x86 程序，
// 体积只有几 KB，启动几十毫秒，且可以用 CREATE_NO_WINDOW 完全静默调用
// —— 不会像 powershell.exe 那样闪黑框。
//
// 用法：
//   XJCodec32.exe <dll目录> lock   <文件> [口令]
//   XJCodec32.exe <dll目录> unlock <文件> [口令]
//   XJCodec32.exe <dll目录> getid
//
// 退出码：0 成功；2 加载 DLL 失败；3 getid 拿不到；9 参数错误
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

class XJCodec32
{
    [DllImport("kernel32", EntryPoint = "LoadLibraryExA", SetLastError = true,
        CharSet = CharSet.Ansi, CallingConvention = CallingConvention.StdCall)]
    static extern IntPtr LoadLibraryEx(string path, IntPtr hFile, uint flags);

    [DllImport("kernel32", EntryPoint = "SetDllDirectoryA", SetLastError = true,
        CharSet = CharSet.Ansi, CallingConvention = CallingConvention.StdCall)]
    static extern bool SetDllDirectory(string path);

    [DllImport("TP.dll", EntryPoint = "DS1", CharSet = CharSet.Ansi,
        CallingConvention = CallingConvention.StdCall)]
    static extern int DS1(string file, string pass);

    [DllImport("TP.dll", EntryPoint = "DS2", CharSet = CharSet.Ansi,
        CallingConvention = CallingConvention.StdCall)]
    static extern int DS2(string file, string pass);

    [DllImport("Socket.dll", EntryPoint = "GetID", CharSet = CharSet.Ansi,
        CallingConvention = CallingConvention.StdCall)]
    static extern IntPtr GetID_std();

    [DllImport("Socket.dll", EntryPoint = "GetID", CharSet = CharSet.Ansi,
        CallingConvention = CallingConvention.Cdecl)]
    static extern IntPtr GetID_cdecl();

    [DllImport("Socket.dll", EntryPoint = "Getini", CharSet = CharSet.Ansi,
        CallingConvention = CallingConvention.StdCall)]
    static extern IntPtr Getini(string name);

    [DllImport("Socket.dll", EntryPoint = "Connect", CharSet = CharSet.Ansi,
        CallingConvention = CallingConvention.StdCall)]
    static extern int Connect(string host, int port);

    const uint LOAD_WITH_ALTERED_SEARCH_PATH = 0x8;

    static int Main(string[] args)
    {
        if (args.Length < 2)
        {
            Console.Error.WriteLine("用法: XJCodec32 <dll目录> lock|unlock|getid|probe [文件] [口令]");
            return 9;
        }
        string dllDir = Path.GetFullPath(args[0]);
        string mode = args[1].ToLowerInvariant();
        string file = args.Length > 2 ? args[2] : "";
        string pass = args.Length > 3 ? args[3] : "xjy.11";

        Directory.SetCurrentDirectory(dllDir);
        SetDllDirectory(dllDir);

        if (mode == "getid" || mode == "probe")
        {
            // 只需要 Socket.dll
            IntPtr hs = LoadLibraryEx(Path.Combine(dllDir, "Socket.dll"), IntPtr.Zero,
                                      LOAD_WITH_ALTERED_SEARCH_PATH);
            if (hs == IntPtr.Zero)
            {
                Console.Error.WriteLine("LoadLibraryEx(Socket.dll) 失败: " + Marshal.GetLastWin32Error());
                return 2;
            }
            if (mode == "getid")
            {
                string id = TryGetId();
                Console.WriteLine(id);
                return string.IsNullOrEmpty(id) ? 3 : 0;
            }
            // probe：把几种调用方式都试一遍，方便诊断
            // 注意：Getini / Connect 会让 socket.dll 访问违例，只记录不实际调用
            Console.WriteLine("Socket.dll 句柄 = " + hs.ToInt64());
            DumpId("GetID (stdcall)", Try(() => GetID_std()));
            DumpId("GetID (cdecl)  ", Try(() => GetID_cdecl()));
            DumpId("再次 GetID     ", Try(() => GetID_std()));
            return 0;
        }

        IntPtr h = LoadLibraryEx(Path.Combine(dllDir, "TP.dll"), IntPtr.Zero,
                                 LOAD_WITH_ALTERED_SEARCH_PATH);
        if (h == IntPtr.Zero)
        {
            Console.Error.WriteLine("LoadLibraryEx(TP.dll) 失败: " + Marshal.GetLastWin32Error());
            return 2;
        }
        if (mode == "lock") { DS1(file, pass); return 0; }
        if (mode == "unlock") { DS2(file, pass); return 0; }
        Console.Error.WriteLine("未知模式: " + mode);
        return 9;
    }

    // ---------- 诊断辅助 ----------
    static IntPtr Try(Func<IntPtr> f)
    {
        try { return f(); } catch (Exception e) { Console.Error.WriteLine("  异常: " + e.Message); return IntPtr.Zero; }
    }

    static int Try2(Func<int> f)
    {
        try { return f(); } catch (Exception e) { Console.Error.WriteLine("  异常: " + e.Message); return -9999; }
    }

    static void DumpId(string label, IntPtr p)
    {
        if (p == IntPtr.Zero) { Console.WriteLine(label + " -> NULL"); return; }
        string ansi = Marshal.PtrToStringAnsi(p);
        string uni = "";
        try { uni = Marshal.PtrToStringUni(p); } catch { }
        Console.WriteLine(label + " -> 指针 " + p.ToInt64()
                          + "  ANSI='" + ansi + "'  Unicode='" + uni + "'");
    }

    static string TryGetId()
    {
        IntPtr p = Try(() => GetID_std());
        if (p != IntPtr.Zero)
        {
            string s = Marshal.PtrToStringAnsi(p);
            if (!string.IsNullOrEmpty(s)) return s;
        }
        p = Try(() => GetID_cdecl());
        if (p != IntPtr.Zero)
        {
            string s = Marshal.PtrToStringAnsi(p);
            if (!string.IsNullOrEmpty(s)) return s;
        }
        return "";
    }
}
