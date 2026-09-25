// ============================================================================
//  TDRadioTool — консольное приложение для работы с кодплагом .td раций TIDRadio.
//
//  Команды:
//    TDRadioTool td2csv <input.td> [output.csv]      — экспорт каналов в CSV
//    TDRadioTool csv2td  <input.csv> <target.td> [output.td] — импорт CSV в .td
//
//  csv2td автоматически определяет формат CSV (канонический или CHIRP),
//  сопоставляет колонки по имени/псевдонимам; если колонка не найдена — в
//  интерактивном режиме предлагает выбрать её из списка или пропустить
//  (для необязательных параметров). Без терминала ненайденные необязательные
//  колонки берут значения по умолчанию.
// ============================================================================

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using TDRadio;

namespace TDRadioTool
{
    internal static class Program
    {
        private const int ChannelCount = 199;

        // Схема параметров канала: ключ, подпись, псевдонимы имён колонок.
        private static readonly string[][] Schema =
        {
            new[] { "ChannelNo",  "Channel No",    "channel no", "channel", "ch", "location", "#", "no" },
            new[] { "RX",         "RX Freq [MHz]", "rx freq", "rx", "rx frequency", "receive frequency" },
            new[] { "TX",         "TX Freq [MHz]", "tx freq", "tx", "tx frequency", "transmit frequency" },
            new[] { "RXTone",     "RX CTCSS/DCS",  "rx ctcss", "rx ctcss/dcs", "rx tone", "rx subaudio", "rx dcs" },
            new[] { "TXTone",     "TX CTCSS/DCS",  "tx ctcss", "tx ctcss/dcs", "tx tone", "tx subaudio", "tx dcs" },
            new[] { "Power",      "Power",         "power", "lmh", "power level", "output power", "sila" },
            new[] { "Bandwidth",  "Bandwidth",     "bandwidth", "band width", "band" },
            new[] { "Scrambler",  "Scrambler",     "scrambler", "scramble", "scrambling" },
            new[] { "PTTId",      "PTT ID",        "ptt id", "pttid", "ptt" },
            new[] { "FreqHop",    "Freq Hop",      "freq hop", "frequency hop", "hop" },
            new[] { "BusyLock",   "Busy Lock",     "busy lock", "busy" },
            new[] { "Scan",       "Scan",          "scan", "scan add", "scanlist", "scanning" },
            new[] { "RxModel",    "Rx Modulation", "rx modulation", "rx model", "modulation", "rx mode" },
            new[] { "Name",       "Channel Name",  "channel name", "name", "display", "display name", "shortcut", "alias" },
        };

        private static readonly HashSet<string> Required = new HashSet<string>(StringComparer.Ordinal) { "ChannelNo", "RX" };

        private static int Main(string[] args)
        {
            EnableUtf8();
            try { return Run(args); }
            catch (Exception ex)
            {
                Console.Error.WriteLine("Ошибка: " + ex.Message);
                return 1;
            }
        }

        private static int Run(string[] args)
        {
            if (args.Length < 1)
            {
                Usage();
                return 1;
            }
            string cmd = args[0].ToLowerInvariant();
            switch (cmd)
            {
                case "td2csv":
                case "td-to-csv":
                    return Td2Csv(args);
                case "csv2td":
                case "csv-to-td":
                    return Csv2Td(args);
                default:
                    Usage();
                    return 1;
            }
        }

        private static void Usage()
        {
            Console.WriteLine("Использование:");
            Console.WriteLine("  TDRadioTool td2csv <input.td> [output.csv]");
            Console.WriteLine("  TDRadioTool csv2td  <input.csv> <target.td> [output.td]");
        }

        // ======================= td2csv =======================

        private static int Td2Csv(string[] args)
        {
            if (args.Length < 2) { Usage(); return 1; }
            string inTd = args[1];
            string outCsv = args.Length > 2 ? args[2] : Path.ChangeExtension(inTd, ".csv");
            int n = new TDRadioCodeplug().ReadFile(inTd).ExportToCSV(outCsv);
            Console.WriteLine("Экспортировано каналов: {0} -> {1}", n, outCsv);
            return 0;
        }

        // ======================= csv2td =======================

        private static int Csv2Td(string[] args)
        {
            if (args.Length < 3) { Usage(); return 1; }
            string csv = args[1];
            string td = args[2];
            string outTd = args.Length > 3 ? args[3] : Path.ChangeExtension(td, null) + "_patched.td";

            string[] lines = File.ReadAllLines(csv, Encoding.UTF8);
            if (lines.Length == 0) throw new InvalidDataException("Пустой CSV-файл.");
            string[] header = SplitCsvLine(lines[0].TrimStart('\uFEFF'));

            string fmt = DetectFormat(header);
            Console.WriteLine("Формат CSV: " + fmt);

            Dictionary<string, int> colmap = fmt == "chirp"
                ? ResolveChirpColumns(header, out _)
                : ResolveCanonicalColumns(header);

            var cp = new TDRadioCodeplug().ReadFile(td);
            int count = 0;
            for (int lineIdx = 1; lineIdx < lines.Length; lineIdx++)
            {
                if (string.IsNullOrWhiteSpace(lines[lineIdx])) continue;
                string[] f = SplitCsvLine(lines[lineIdx].Trim());
                ChannelRecord rc = fmt == "chirp"
                    ? BuildChirpRow(f, colmap, lineIdx)
                    : BuildCanonicalRow(f, colmap, lineIdx);
                if (rc == null || rc.RxFrequencyMHz <= 0) continue;
                if (rc.Number < 1 || rc.Number > ChannelCount) continue;
                cp.SetChannel(rc);
                count++;
            }

            cp.WriteFile(outTd);
            Console.WriteLine("Каналов записано: {0} -> {1}", count, outTd);
            return 0;
        }

        // ======================= определение формата =======================

        private static string DetectFormat(string[] header)
        {
            // Узкие маркеры: голые "rx"/"tx" здесь не используются, т.к. встречаются
            // внутри названий вроде "RxDtcsCode" и могли бы дать ложное определение.
            if (FindCol(header, "rx freq", "rx frequency", "receive frequency", "frequency [mhz]", "rx f") >= 0) return "canonical";
            if (FindCol(header, "frequency") >= 0 && FindCol(header, "duplex") >= 0) return "chirp";
            return "canonical";
        }

        // ======================= канонический формат =======================

        private static Dictionary<string, int> ResolveCanonicalColumns(string[] header)
        {
            string[] norm = NormAll(header);
            var colmap = new Dictionary<string, int>(StringComparer.Ordinal);
            var issues = new List<string>();
            var claims = new Dictionary<int, List<string>>();

            for (int p = 0; p < Schema.Length; p++)
            {
                string key = Schema[p][0];
                var aliases = new List<string>();
                for (int a = 2; a < Schema[p].Length; a++) aliases.Add(Norm(Schema[p][a]));

                var exact = new List<int>();
                var sub = new List<int>();
                for (int i = 0; i < norm.Length; i++)
                {
                    if (aliases.Contains(norm[i])) exact.Add(i);
                    else if (SubMatch(norm[i], aliases)) sub.Add(i);
                }
                var hits = exact.Count > 0 ? exact : sub;
                if (hits.Count == 0)
                {
                    colmap[key] = -1;
                    issues.Add("Нет колонки для параметра '" + Schema[p][1] + "'");
                    continue;
                }
                colmap[key] = hits[0];
                if (!claims.ContainsKey(hits[0])) claims[hits[0]] = new List<string>();
                claims[hits[0]].Add(Schema[p][1]);
                if (hits.Count > 1)
                    issues.Add("Неоднозначность '" + Schema[p][1] + "': " + JoinIndexed(header, hits));
            }

            foreach (var kv in claims)
                if (kv.Value.Count > 1)
                    issues.Add("Колонка '[" + (kv.Key + 1) + "] " + header[kv.Key] + "' используется параметрами: " + string.Join(", ", kv.Value));

            bool interactive = !Console.IsInputRedirected;

            if (issues.Count > 0 || colmap.ContainsValue(-1))
            {
                PrintColumns(header);
                foreach (string it in issues) Console.WriteLine("  КОЛЛИЗИЯ: " + it);
            }

            if (interactive)
            {
                for (int p = 0; p < Schema.Length; p++)
                    if (colmap[Schema[p][0]] == -1)
                        PromptColumn(colmap, header, Schema[p][0], Schema[p][1]);
            }

            Console.WriteLine("Сопоставление колонок:");
            for (int p = 0; p < Schema.Length; p++)
            {
                int idx = colmap[Schema[p][0]];
                Console.WriteLine("  {0,-16} -> {1}",
                    Schema[p][1], idx >= 0 ? "[" + (idx + 1) + "] " + header[idx] : "<не задано>");
            }
            return colmap;
        }

        private static void PromptColumn(Dictionary<string, int> colmap, string[] header, string key, string label)
        {
            bool required = Required.Contains(key);
            Console.WriteLine("Параметр '" + label + "' не найден среди колонок.");
            if (required) Console.WriteLine("  Он обязательный. Введите номер колонки из списка выше.");
            else Console.WriteLine("  Введите номер колонки либо 0/Enter, чтобы пропустить (значение по умолчанию).");

            for (int attempt = 0; attempt < 8; attempt++)
            {
                Console.Write("  > ");
                string raw = Console.ReadLine();
                if (raw == null) raw = "";
                raw = raw.Trim();
                if (raw == "")
                {
                    if (required && key != "ChannelNo")
                    {
                        Console.WriteLine("  Обязательный параметр '" + label + "' нельзя пропустить.");
                        continue;
                    }
                    colmap[key] = -1;
                    if (key == "ChannelNo") Console.WriteLine("  Channel No пропущен: номера будут назначены по порядку.");
                    else Console.WriteLine("  " + label + " пропущен (по умолчанию).");
                    return;
                }
                if (!int.TryParse(raw, out int n))
                {
                    Console.WriteLine("  Введите целый номер колонки.");
                    continue;
                }
                if (n == 0)
                {
                    if (required) { Console.WriteLine("  Обязательный параметр '" + label + "' нельзя пропустить."); continue; }
                    colmap[key] = -1;
                    Console.WriteLine("  " + label + " пропущен (по умолчанию).");
                    return;
                }
                if (!(1 <= n && n <= header.Length))
                {
                    Console.WriteLine("  Номер вне диапазона 1.." + header.Length + ".");
                    continue;
                }
                if (colmap.ContainsValue(n - 1))
                {
                    Console.WriteLine("  Колонка '[" + n + "] " + header[n - 1] + "' уже используется другим параметром.");
                    continue;
                }
                colmap[key] = n - 1;
                Console.WriteLine("  " + label + " -> колонка [" + n + "] " + header[n - 1]);
                return;
            }
            colmap[key] = -1;
            if (required && key != "ChannelNo")
                throw new InvalidDataException("Не удалось сопоставить обязательный параметр '" + label + "'");
        }

        private static ChannelRecord BuildCanonicalRow(string[] f, Dictionary<string, int> m, int lineIdx)
        {
            int n;
            if (m["ChannelNo"] >= 0) { int.TryParse(Text(f, m["ChannelNo"]), out n); }
            else n = lineIdx; // порядковый номер строки
            if (n < 1 || n > ChannelCount) return null;

            double rx = ParseFreq(Text(f, m["RX"]));
            if (rx <= 0) return null;

            return new ChannelRecord
            {
                Number = n,
                RxFrequencyMHz = rx,
                TxFrequencyMHz = ParseFreq(Text(f, m["TX"])),
                RXTone = Text(f, m["RXTone"]),
                TXTone = Text(f, m["TXTone"]),
                Power = ParsePower(Text(f, m["Power"])),
                Bandwidth = Text(f, m["Bandwidth"]).Trim().Equals("Narrow", StringComparison.OrdinalIgnoreCase) ? ChannelBand.Narrow : ChannelBand.Wide,
                Scrambler = ParseInt(Text(f, m["Scrambler"])),
                PTTId = ParsePtt(Text(f, m["PTTId"])),
                FrequencyHop = IsOn(Text(f, m["FreqHop"])),
                BusyLock = IsOn(Text(f, m["BusyLock"])),
                InScanList = IsYes(Text(f, m["Scan"])),
                Modulation = Text(f, m["RxModel"]).Trim().Equals("AM", StringComparison.OrdinalIgnoreCase) ? RxModulation.AM : RxModulation.FM,
                Name = Text(f, m["Name"]),
            };
        }

        // ======================= CHIRP формат =======================

        private static Dictionary<string, int> ResolveChirpColumns(string[] header, out List<string> issues)
        {
            issues = new List<string>();
            var keys = new[] { "Location", "Name", "Frequency", "Duplex", "Offset", "Tone", "rToneFreq",
                "cToneFreq", "DtcsCode", "DtcsPolarity", "RxDtcsCode", "Mode", "Skip", "Power" };
            var map = new Dictionary<string, int>(StringComparer.Ordinal);
            foreach (string k in keys)
            {
                int idx = k switch
                {
                    "Location" => FindColExact(header, "location"),
                    "Name" => FindColExact(header, "name"),
                    "Frequency" => FindCol(header, "frequency"),
                    "Duplex" => FindCol(header, "duplex"),
                    "Offset" => FindCol(header, "offset"),
                    "Tone" => FindColExact(header, "tone"),
                    "rToneFreq" => FindCol(header, "rtonefreq"),
                    "cToneFreq" => FindCol(header, "ctonefreq"),
                    "DtcsCode" => FindCol(header, "dtcscode"),
                    "DtcsPolarity" => FindCol(header, "dtcspolarity"),
                    "RxDtcsCode" => FindCol(header, "rxdtcscode"),
                    "Mode" => FindColExact(header, "mode"),
                    "Skip" => FindCol(header, "skip"),
                    "Power" => FindCol(header, "power", "rfpower"),
                    _ => -1,
                };
                map[k] = idx;
            }
            return map;
        }

        private static ChannelRecord BuildChirpRow(string[] f, Dictionary<string, int> m, int lineIdx)
        {
            int n;
            int.TryParse(Text(f, m["Location"]), out n);
            if (n < 1 || n > ChannelCount) n = lineIdx;

            double rx = ParseFreq(Text(f, m["Frequency"]));
            if (rx <= 0) return null;

            string duplex = Text(f, m["Duplex"]).Trim().ToLowerInvariant();
            double off = ParseFreq(Text(f, m["Offset"]));
            double tx = rx;
            if (duplex == "+" && off > 0) tx = rx + off;
            else if (duplex == "-" && off > 0) tx = rx - off;
            else if (duplex == "split" && off > 0) tx = off;
            if (tx <= 0) tx = rx;

            string dcs = Text(f, m["DtcsCode"]); if (string.IsNullOrWhiteSpace(dcs)) dcs = Text(f, m["RxDtcsCode"]);
            string pol = Text(f, m["DtcsPolarity"]);
            string digits = "";
            foreach (char c in dcs) if (char.IsDigit(c)) digits += c;
            string tone;
            if (digits.Length >= 3)
                tone = "D" + digits + (pol.Trim().ToUpperInvariant().StartsWith("I") ? "I" : "N");
            else
            {
                string ct = Text(f, m["cToneFreq"]), rt = Text(f, m["rToneFreq"]);
                tone = !string.IsNullOrWhiteSpace(ct) ? ct : rt;
                if (string.IsNullOrWhiteSpace(tone)) tone = "";
            }

            string mode = Text(f, m["Mode"]).Trim().ToLowerInvariant();
            string pwr = Text(f, m["Power"]).Trim().ToLowerInvariant();
            PowerLevel power = PowerLevel.High;
            if (pwr.Contains("low")) power = PowerLevel.Low;
            else if (pwr.Contains("mid")) power = PowerLevel.Mid;

            string skip = Text(f, m["Skip"]).Trim();
            bool scan = !(skip == "*" || skip.Equals("skip", StringComparison.OrdinalIgnoreCase));

            return new ChannelRecord
            {
                Number = n,
                RxFrequencyMHz = rx,
                TxFrequencyMHz = tx,
                RXTone = tone,
                TXTone = tone,
                Power = power,
                Bandwidth = mode == "nfm" ? ChannelBand.Narrow : ChannelBand.Wide,
                Modulation = mode == "am" ? RxModulation.AM : RxModulation.FM,
                InScanList = scan,
                Name = Text(f, m["Name"]),
            };
        }

        // ======================= помощники =======================

        private static void EnableUtf8()
        {
            try { Console.OutputEncoding = Encoding.UTF8; } catch { }
            try { Console.InputEncoding = Encoding.UTF8; } catch { }
        }

        private static string[] NormAll(string[] header)
        {
            var r = new string[header.Length];
            for (int i = 0; i < header.Length; i++) r[i] = Norm(header[i]);
            return r;
        }

        private static string Norm(string s) => (s ?? "").Trim().ToLowerInvariant().Replace("_", " ");

        private static bool SubMatch(string h, List<string> aliases)
        {
            foreach (string a in aliases) if (h.Contains(a)) return true;
            return false;
        }

        private static string JoinIndexed(string[] header, List<int> idx)
        {
            var parts = new List<string>();
            foreach (int i in idx) parts.Add("[" + (i + 1) + "] " + header[i]);
            return string.Join(", ", parts);
        }

        private static void PrintColumns(string[] header)
        {
            Console.WriteLine("Колонки CSV (" + header.Length + "):");
            for (int i = 0; i < header.Length; i++) Console.WriteLine("  [" + (i + 1) + "] " + header[i]);
        }

        private static int FindCol(string[] header, params string[] aliases)
        {
            if (header == null) return -1;
            string[] norm = NormAll(header);
            for (int exact = 1; exact >= 0; exact--)
                foreach (string a in aliases)
                {
                    string key = Norm(a);
                    for (int i = 0; i < norm.Length; i++)
                        if ((exact == 1 && norm[i] == key) || (exact == 0 && norm[i].Contains(key))) return i;
                }
            return -1;
        }

        private static int FindColExact(string[] header, string name)
        {
            if (header == null) return -1;
            for (int i = 0; i < header.Length; i++)
                if (Norm(header[i]) == Norm(name)) return i;
            return -1;
        }

        private static string Text(string[] f, int col)
        {
            return (col >= 0 && col < f.Length) ? (f[col] ?? "") : "";
        }

        private static double ParseFreq(string s)
        {
            if (string.IsNullOrWhiteSpace(s)) return 0;
            return double.TryParse(s.Trim().Replace(',', '.'), NumberStyles.Float, CultureInfo.InvariantCulture, out double d) ? d : 0;
        }

        private static int ParseInt(string s)
        {
            return int.TryParse(s.Trim(), out int v) ? v : 0;
        }

        private static PowerLevel ParsePower(string s)
        {
            string t = s.Trim().ToLowerInvariant();
            if (t == "low") return PowerLevel.Low;
            if (t == "mid" || t == "medium") return PowerLevel.Mid;
            return PowerLevel.High;
        }

        private static PttIdMode ParsePtt(string s)
        {
            switch (s.Trim().ToLowerInvariant())
            {
                case "begin": return PttIdMode.Begin;
                case "end": return PttIdMode.End;
                case "both": return PttIdMode.Both;
                default: return PttIdMode.Off;
            }
        }

        private static bool IsOn(string s) => s.Trim().Equals("On", StringComparison.OrdinalIgnoreCase) || s.Trim().Equals("Yes", StringComparison.OrdinalIgnoreCase);
        private static bool IsYes(string s) => s.Trim().Equals("Yes", StringComparison.OrdinalIgnoreCase) || s.Trim().Equals("On", StringComparison.OrdinalIgnoreCase);

        private static string[] SplitCsvLine(string line)
        {
            var fields = new List<string>();
            var sb = new StringBuilder();
            bool inQuotes = false;
            for (int i = 0; i < line.Length; i++)
            {
                char c = line[i];
                if (inQuotes)
                {
                    if (c == '"') { if (i + 1 < line.Length && line[i + 1] == '"') { sb.Append('"'); i++; } else inQuotes = false; }
                    else sb.Append(c);
                }
                else
                {
                    if (c == '"') inQuotes = true;
                    else if (c == ',') { fields.Add(sb.ToString()); sb.Clear(); }
                    else sb.Append(c);
                }
            }
            fields.Add(sb.ToString());
            return fields.ToArray();
        }
    }
}