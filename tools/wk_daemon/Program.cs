using System.Diagnostics;
using System.Reflection;
using Microsoft.Extensions.Hosting;
using WolvenKit.Common;

namespace WolvenKitDaemon;

public static class Program
{
    public static void Main(string[] args)
    {
        var realOut = Console.Out;
        Console.SetOut(TextWriter.Null);
        Console.SetError(TextWriter.Null);

        var cliAsm = Assembly.LoadFrom(Path.Combine(AppContext.BaseDirectory, "WolvenKit.CLI.dll"));
        var ghType = cliAsm.GetType("WolvenKit.CLI.GenericHost")!;
        var createHostMethod = ghType.GetMethod(
            "CreateHostBuilder",
            BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static
        )!;
        var hb = (IHostBuilder)createHostMethod.Invoke(null, new object[] { Array.Empty<string>() })!;
        var host = hb.Build();

        var ucType = cliAsm.GetType("CP77Tools.Commands.UncookCommand")!;
        var cmd = Activator.CreateInstance(ucType, nonPublic: true)!;
        var actionMethod = ucType.GetMethod(
            "Action",
            BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance
        )!;

        var uaType = cliAsm.GetType("CP77Tools.Commands.UncookCommand+UncookArguments")!;
        var pathProp = uaType.GetProperty("path")!;
        var outDirInfoProp = uaType.GetProperties()
            .First(p => p.Name == "outpath" && p.PropertyType == typeof(DirectoryInfo));
        var outStringProp = uaType.GetProperties()
            .First(p => p.Name == "outpath" && p.PropertyType == typeof(string));
        var regexProp = uaType.GetProperty("regex")!;
        var uextProp = uaType.GetProperty("uext")!;

        realOut.WriteLine("READY");
        realOut.Flush();

        string? line;
        while ((line = Console.ReadLine()) != null)
        {
            if (string.IsNullOrWhiteSpace(line)) continue;
            if (line == "EXIT") break;

            var sw = Stopwatch.StartNew();
            try
            {
                // Format: outDir \t regex \t arch1|arch2|...
                var parts = line.Split('\t');
                var outDir = parts[0];
                var regex = parts[1];
                var archPaths = parts[2]
                    .Split('|', StringSplitOptions.RemoveEmptyEntries)
                    .Select(p => (FileSystemInfo)new FileInfo(p))
                    .ToArray();

                Directory.CreateDirectory(outDir);
                var ua = Activator.CreateInstance(uaType, nonPublic: true)!;
                pathProp.SetValue(ua, archPaths);
                outStringProp.SetValue(ua, outDir);
                outDirInfoProp.SetValue(ua, new DirectoryInfo(outDir));
                regexProp.SetValue(ua, regex);
                uextProp.SetValue(ua, (EUncookExtension?)EUncookExtension.png);

                actionMethod.Invoke(cmd, new object[] { ua, host });
                sw.Stop();
                realOut.WriteLine($"OK\t{sw.ElapsedMilliseconds}");
                realOut.Flush();
            }
            catch (Exception ex)
            {
                sw.Stop();
                var msg = (ex.InnerException ?? ex).Message.Replace('\r', ' ').Replace('\n', ' ');
                realOut.WriteLine($"ERR\t{sw.ElapsedMilliseconds}\t{msg}");
                realOut.Flush();
            }
        }
    }
}
