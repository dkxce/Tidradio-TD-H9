// ============================================================================
//  TDRadioCodeplug.cs
//  Класс для чтения/записи/конвертации кодплага .td раций TIDRadio (TD-CPS).
//
//  Формат файла .td (подробно описан в README.md):
//    - Сырой дамп EEPROM-образа, 65536 байт (0x10000), пустые байты = 0xFF.
//    - Байты 0..7  : маркер модели "MD-760P" + 0xFF (проверяется при открытии).
//    - 16..3200    : 199 каналов по 16 байт.
//    - 3392..4984  : имена каналов (199 x 8, GB2312).
//    - 3216..      : общие настройки (keyConfig, optionConfig, bandConfig и т.д.).
//    - 6144..6368  : DTMF-коды.
//    - 6400/6432   : бит-карты валидности каналов и списка сканирования (25 байт).
//    - 6480/6496   : VFO A / VFO B (по 16 байт) + сдвиг частоты на 3248.
//    - 3280/6464/6512 : FM-радио (25 каналов x 4, бит-карта, VFO).
//    - 3234/3238   : FM-настройки (режим/мониторинг, текущий канал).
//    - 7168/7184/7200 : загрузочные сообщения bootMsg1..3.
//    - 7968..7983  : micGain, язык, стиль дисплея, цвет меню, VFO-скан, зависание скана.
//
//  Требования: .NET Standard 2.0+ / .NET Core 3.1+.
//    Для кодирования имён GB2312 нужно зарегистрировать провайдера кодировок:
//      Encoding.RegisterProvider(CodePagesEncodingProvider.Instance);
// ============================================================================

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;

namespace TDRadio
{
    /// <summary>Уровень мощности передачи.</summary>
    public enum PowerLevel
    {
        /// <summary>Низкий.</summary>
        Low = 0,
        /// <summary>Средний.</summary>
        Mid = 1,
        /// <summary>Высокий.</summary>
        High = 2,
    }

    /// <summary>Ширина полосы канала.</summary>
    public enum ChannelBand
    {
        /// <summary>Широкая (25 кГц).</summary>
        Wide = 0,
        /// <summary>Узкая (12.5 кГц).</summary>
        Narrow = 1,
    }

    /// <summary>Модуляция приёма.</summary>
    public enum RxModulation
    {
        /// <summary>FM.</summary>
        FM = 0,
        /// <summary>AM.</summary>
        AM = 1,
    }

    /// <summary>Режим PTT ID (идентификации при нажатии PTT).</summary>
    public enum PttIdMode
    {
        /// <summary>Выключен.</summary>
        Off = 0,
        /// <summary>В начале передачи.</summary>
        Begin = 1,
        /// <summary>В конце передачи.</summary>
        End = 2,
        /// <summary>В начале и в конце.</summary>
        Both = 3,
    }

    /// <summary>Направление сдвига частоты (для репитеров).</summary>
    public enum FreqOffsetDirection
    {
        /// <summary>Без сдвига.</summary>
        Off = 0,
        /// <summary>Минус (TX = RX - сдвиг).</summary>
        Minus = 1,
        /// <summary>Плюс (TX = RX + сдвиг).</summary>
        Plus = 2,
    }

    /// <summary>Режим работы FM-радио (частоты ниже 108 МГц).</summary>
    public enum FmMode
    {
        /// <summary>VFO (прямой ввод частоты).</summary>
        VFO = 0,
        /// <summary>Канал (выбранный из списка).</summary>
        Channel = 1,
    }

    // ==========================================================================
    //  МОДЕЛИ ДАННЫХ
    // ==========================================================================

    /// <summary>
    /// Запись одного канала (16 байт в EEPROM). Предоставляет типизированный доступ
    /// к частотам, субтонам и битовым флагам. Для передачи в радиоблок используется
    /// <see cref="Serialize"/> / <see cref="Deserialize"/>.
    /// </summary>
    public sealed class ChannelRecord
    {
        /// <summary>Номер канала (1..199).</summary>
        public int Number { get; set; } = 1;

        /// <summary>Частота приёма, МГц (0 = не задана).</summary>
        public double RxFrequencyMHz { get; set; }

        /// <summary>Частота передачи, МГц (0 = как приём).</summary>
        public double TxFrequencyMHz { get; set; }

        /// <summary>RX-субтон: "OFF", "88.5" (CTCSS) или "D023N"/"D023I" (DCS).</summary>
        public string RXTone { get; set; } = "OFF";

        /// <summary>TX-субтон: формат как у <see cref="RXTone"/>.</summary>
        public string TXTone { get; set; } = "OFF";

        /// <summary>Группа скремблера (0..16).</summary>
        public int Scrambler { get; set; }

        /// <summary>Уровень мощности.</summary>
        public PowerLevel Power { get; set; } = PowerLevel.High;

        /// <summary>Ширина полосы.</summary>
        public ChannelBand Bandwidth { get; set; } = ChannelBand.Wide;

        /// <summary>Режим PTT ID.</summary>
        public PttIdMode PTTId { get; set; } = PttIdMode.Off;

        /// <summary>Включён ли «прыжок по частоте».</summary>
        public bool FrequencyHop { get; set; }

        /// <summary>Включена ли блокировка по занятости.</summary>
        public bool BusyLock { get; set; }

        /// <summary>Модуляция приёма.</summary>
        public RxModulation Modulation { get; set; } = RxModulation.FM;

        /// <summary>Входит ли канал в список сканирования.</summary>
        public bool InScanList { get; set; }

        /// <summary>Имя канала (до 8 символов).</summary>
        public string Name { get; set; } = "";

        /// <summary>Сбросить запись в состояние «пустой канал».</summary>
        public void Clear()
        {
            Number = 1;
            RxFrequencyMHz = 0;
            TxFrequencyMHz = 0;
            RXTone = "OFF";
            TXTone = "OFF";
            Scrambler = 0;
            Power = PowerLevel.High;
            Bandwidth = ChannelBand.Wide;
            PTTId = PttIdMode.Off;
            FrequencyHop = false;
            BusyLock = false;
            Modulation = RxModulation.FM;
            InScanList = false;
            Name = "";
        }
    }

    /// <summary>
    /// Запись VFO (16 байт). Используется для блоков VFO A и VFO B. Отличается от
    /// канала только набором битовых полей (нет «прыжка по частоте» в byte13).
    /// </summary>
    public sealed class VfoRecord
    {
        /// <summary>Частота приёма, МГц.</summary>
        public double RxFrequencyMHz { get; set; }

        /// <summary>Частота передачи, МГц (0 = как приём).</summary>
        public double TxFrequencyMHz { get; set; }

        /// <summary>RX-субтон ("OFF"/CTCSS/DCS).</summary>
        public string RXTone { get; set; } = "OFF";

        /// <summary>TX-субтон.</summary>
        public string TXTone { get; set; } = "OFF";

        /// <summary>Значение скремблера.</summary>
        public int Scrambler { get; set; }

        /// <summary>Режим PTT ID.</summary>
        public PttIdMode PTTId { get; set; } = PttIdMode.Off;

        /// <summary>Включён ли «прыжок по частоте».</summary>
        public bool FrequencyHop { get; set; }

        /// <summary>Включена ли блокировка по занятости.</summary>
        public bool BusyLock { get; set; }

        /// <summary>Включён ли скремблер.</summary>
        public bool ScramblerEnable { get; set; }

        /// <summary>Уровень мощности.</summary>
        public PowerLevel Power { get; set; } = PowerLevel.High;

        /// <summary>Ширина полосы.</summary>
        public ChannelBand Bandwidth { get; set; } = ChannelBand.Wide;

        /// <summary>Направление сдвига частоты.</summary>
        public FreqOffsetDirection OffsetDirection { get; set; } = FreqOffsetDirection.Off;

        /// <summary>Модуляция приёма.</summary>
        public RxModulation Modulation { get; set; } = RxModulation.FM;

        /// <summary>Величина сдвига частоты, МГц (хранится отдельным блоком на 3248).</summary>
        public double FrequencyOffsetMHz { get; set; }
    }

    /// <summary>
    /// FM-радио канал (частоты вещания 76..108 МГц). В EEPROM занимает 4 байта,
    /// значащи manтолько первые 2 (BCD-частота с шагом 0.1 МГц).
    /// </summary>
    public sealed class FmChannelRecord
    {
        /// <summary>Номер FM-канала (1..25).</summary>
        public int Number { get; set; } = 1;

        /// <summary>Частота, МГц (0 = не задана).</summary>
        public double FrequencyMHz { get; set; }

        /// <summary>Канал включён/валиден.</summary>
        public bool Enabled { get; set; }
    }

    // ==========================================================================
    //  ГЛАВНЫЙ КЛАСС
    // ==========================================================================

    /// <summary>
    /// Класс для работы с файлом кодплага .td раций TIDRadio (TD-CPS).
    /// <para>
    /// Хранит полный образ EEPROM в памяти (см. <see cref="ReadFile"/>), позволяет
    /// читать и изменять настройки каналов, VFO, FM-радио, загрузочных сообщений,
    /// микрофонного усиления и прочее, а также конвертировать в CSV и обратно.
    /// </para>
    /// <para>Все записи проверяют значения и выбрасывают <see cref="ArgumentOutOfRangeException"/>
    /// при выходе из допустимого диапазона.</para>
    /// </summary>
    public sealed class TDRadioCodeplug
    {
        // ------------------------------ Константы ------------------------------

        /// <summary>Размер полного EEPROM-образа в байтах.</summary>
        public const int EEROM_SPACE = 0x10000;                 // 65536

        /// <summary>Смещение начала данных каналов.</summary>
        public const int CHANNEL_START = 16;
        /// <summary>Количество каналов.</summary>
        public const int CHANNEL_COUNT = 199;
        /// <summary>Размер записи одного канала в байтах.</summary>
        public const int CHANNEL_SIZE = 16;

        /// <summary>Смещение блока имён каналов.</summary>
        public const int CHNAME_START = 3392;
        /// <summary>Максимальное число байт имени канала.</summary>
        public const int CHNAME_SIZE = 8;

        /// <summary>Смещение бит-карты валидности каналов.</summary>
        public const int CHINDEX_START = 6400;
        /// <summary>Смещение бит-карты списка сканирования.</summary>
        public const int SCANINDEX_START = 6432;
        /// <summary>Длина бит-карт (199 бит = 25 байт).</summary>
        public const int INDEX_LEN = 25;

        /// <summary>Смещение общих настроек (GeneralSet).</summary>
        public const int GENERAL_SET_START = 3216;

        /// <summary>Смещение сдвига частоты VFO (8 байт).</summary>
        public const int FREQ_OFFSET_START = 3248;

        /// <summary>Смещение FM-каналов (25 x 4 байта).</summary>
        public const int FM_CHANNELS_START = 3280;
        /// <summary>Число FM-каналов.</summary>
        public const int FM_CHANNEL_COUNT = 25;
        /// <summary>Смещение бит-карты валидности FM-каналов.</summary>
        public const int FM_VALID_START = 6464;
        /// <summary>Смещение FM-VFO частоты.</summary>
        public const int FM_VFO_START = 6512;
        /// <summary>Смещение FM-настроек (рабочий режим/мониторинг).</summary>
        public const int FM_SETTINGS_START = 3234;
        /// <summary>Смещение текущего FM-канала.</summary>
        public const int FM_CURRENT_CHANNEL_START = 3238;

        /// <summary>Смещение `stunCode` DTMF.</summary>
        public const int DTMF_STUN_START = 6144;
        /// <summary>Смещение `killCode` DTMF.</summary>
        public const int DTMF_KILL_START = 6160;
        /// <summary>Смещение локального ID DTMF.</summary>
        public const int DTMF_LOCAL_ID_START = 6176;
        /// <summary>Смещение кода группы DTMF.</summary>
        public const int DTMF_GROUP_CODE_START = 6185;
        /// <summary>Смещение первого кода-группы DTMF.</summary>
        public const int DTMF_CODE_GROUP1_START = 6192;
        /// <summary>Смещение стартового кода DTMF.</summary>
        public const int DTMF_START_CODE_START = 6336;
        /// <summary>Смещение конечного кода DTMF.</summary>
        public const int DTMF_END_CODE_START = 6352;

        /// <summary>Смещение VFO A.</summary>
        public const int VFO_A_START = 6480;
        /// <summary>Смещение VFO B.</summary>
        public const int VFO_B_START = 6496;

        /// <summary>Смещение bootMsg1.</summary>
        public const int BOOT_MSG1_START = 7168;
        /// <summary>Смещение bootMsg2.</summary>
        public const int BOOT_MSG2_START = 7184;
        /// <summary>Смещение bootMsg3.</summary>
        public const int BOOT_MSG3_START = 7200;
        /// <summary>Длина загрузочного сообщения.</summary>
        public const int BOOT_MSG_LEN = 16;

        /// <summary>Смещение микрофонного усиления.</summary>
        public const int MIC_GAIN_START = 7968;
        /// <summary>Смещение выбора языка.</summary>
        public const int LANGUAGE_SELECT_START = 7976;
        /// <summary>Смещение стиля дисплея.</summary>
        public const int DISPLAY_STYLE_START = 7977;
        /// <summary>Смещение цвета меню.</summary>
        public const int MENU_COLOR_START = 7978;
        /// <summary>Смещение верхнего предела сканирования VFO.</summary>
        public const int VFO_SCAN_UPPER_START = 7979;
        /// <summary>Смещение нижнего предела сканирования VFO.</summary>
        public const int VFO_SCAN_LOWER_START = 7981;
        /// <summary>Смещение времени зависания скана.</summary>
        public const int SCAN_HANG_TIME_START = 7983;

        /// <summary>Маркер модели, записываемый в байты 0..7 при <see cref="NewFile"/>.</summary>
        public static readonly byte[] MODEL_MARKER = { 0x4D, 0x44, 0x2D, 0x37, 0x36, 0x30, 0x50, 0xFF }; // "MD-760P"

        private const string CSVDelimiter = ",";

        private readonly byte[] _data = new byte[EEROM_SPACE];

        // ------------------------------ Публичные свойства ------------------------------

        /// <summary>Копия текущего образа EEPROM (65536 байт).</summary>
        public byte[] Data
        {
            get { return (byte[])_data.Clone(); }
            set
            {
                if (value == null || value.Length != EEROM_SPACE)
                    throw new ArgumentException("Размер данных должен быть равен 65536 байт", nameof(value));
                Array.Copy(value, _data, EEROM_SPACE);
            }
        }

        // ==========================================================================
        //  ФАЙЛОВЫЕ ОПЕРАЦИИ
        // ==========================================================================

        /// <summary>
        /// Создаёт новый пустой кодплаг: весь образ заполняется 0xFF, в байты 0..7
        /// записывается маркер модели. Используйте как основу перед наполнением.
        /// </summary>
        /// <returns>Возвращает <see langword="this"/> для цепочечного вызова.</returns>
        public TDRadioCodeplug NewFile()
        {
            for (int i = 0; i < EEROM_SPACE; i++) _data[i] = 0xFF;
            Array.Copy(MODEL_MARKER, 0, _data, 0, MODEL_MARKER.Length);
            return this;
        }

        /// <summary>
        /// Читает файл .td с диска и заполняет внутренний образ.
        /// </summary>
        /// <param name="path">Путь к файлу .td.</param>
        /// <returns>Возвращает <see langword="this"/>.</returns>
        /// <exception cref="FileNotFoundException">Файл не найден.</exception>
        /// <exception cref="InvalidDataException">Файл имеет неверный размер или маркер модели.</exception>
        public TDRadioCodeplug ReadFile(string path)
        {
            if (path == null) throw new ArgumentNullException(nameof(path));
            if (!File.Exists(path)) throw new FileNotFoundException("Файл не найден", path);
            byte[] src = File.ReadAllBytes(path);
            if (src.Length != EEROM_SPACE)
                throw new InvalidDataException(
                    string.Format("Неверный размер файла: {0} байт (ожидалось {1}).", src.Length, EEROM_SPACE));

            bool markerOk = IsAllFF(src, 0, 8) || IsEqual(src, 0, MODEL_MARKER);
            if (!markerOk)
                throw new InvalidDataException("Маркер модели в байтах 0..7 не совпадает с ожидаемым (пусто/\"MD-760P\").");

            Array.Copy(src, _data, EEROM_SPACE);
            return this;
        }

        /// <summary>
        /// Записывает текущий образ в файл .td.
        /// </summary>
        /// <param name="path">Путь к выходному файлу .td.</param>
        /// <returns>Возвращает <see langword="this"/>.</returns>
        public TDRadioCodeplug WriteFile(string path)
        {
            if (path == null) throw new ArgumentNullException(nameof(path));
            File.WriteAllBytes(path, _data);
            return this;
        }

        /// <summary>Возвращает тело образа как копию массива.</summary>
        /// <returns>Копия массива байт образа.</returns>
        public byte[] ToArray()
        {
            return (byte[])_data.Clone();
        }

        /// <summary>Загружает образ из массива байт (копирование).</summary>
        /// <param name="raw">Массив ровно 65536 байт.</param>
        /// <returns>Возвращает <see langword="this"/>.</returns>
        public TDRadioCodeplug FromArray(byte[] raw)
        {
            Data = raw;
            return this;
        }

        // ==========================================================================
        //  НИЗКОУРОВНЕВЫЙ ДОСТУП К БАЙТАМ
        // ==========================================================================

        /// <summary>Читает один байт.</summary>
        /// <param name="offset">Смещение 0..65535.</param>
        /// <returns>Значение байта.</returns>
        public byte ReadByte(int offset)
        {
            ValidateOffset(offset, 1);
            return _data[offset];
        }

        /// <summary>Записывает один байт.</summary>
        /// <param name="offset">Смещение 0..65535.</param>
        /// <param name="value">Значение.</param>
        public void WriteByte(int offset, byte value)
        {
            ValidateOffset(offset, 1);
            _data[offset] = value;
        }

        /// <summary>Читает блок байт как копию.</summary>
        /// <param name="offset">Начальное смещение.</param>
        /// <param name="length">Количество байт.</param>
        /// <returns>Массив прочитанных байт.</returns>
        public byte[] ReadBytes(int offset, int length)
        {
            if (length < 0) throw new ArgumentOutOfRangeException(nameof(length));
            ValidateOffset(offset, length);
            var result = new byte[length];
            Array.Copy(_data, offset, result, 0, length);
            return result;
        }

        /// <summary>Записывает блок байт.</summary>
        /// <param name="offset">Начальное смещение.</param>
        /// <param name="value">Записываемые байты.</param>
        public void WriteBytes(int offset, byte[] value)
        {
            if (value == null) throw new ArgumentNullException(nameof(value));
            ValidateOffset(offset, value.Length);
            Array.Copy(value, 0, _data, offset, value.Length);
        }

        // ==========================================================================
        //  КАНАЛЫ
        // ==========================================================================

        /// <summary>
        /// Возвращает канал по номеру (1..199). Невалидный (пустой) канал возвращается
        /// с нулевой частотой.
        /// </summary>
        /// <param name="number">Номер канала 1..199.</param>
        /// <returns>Запись канала <see cref="ChannelRecord"/>.</returns>
        public ChannelRecord GetChannel(int number)
        {
            int idx = RequireChannelIndex(number);
            int baseAddr = CHANNEL_START + idx * CHANNEL_SIZE;
            var ch = new ChannelRecord
            {
                Number = number,
                RxFrequencyMHz = DecodeFrequency(_data, baseAddr + 0),
                TxFrequencyMHz = DecodeFrequency(_data, baseAddr + 4),
                RXTone = DecodeTone(_data, baseAddr + 8),
                TXTone = DecodeTone(_data, baseAddr + 10),
                Scrambler = _data[baseAddr + 12],
                Name = DecodeName(CHNAME_START + idx * CHNAME_SIZE),
            };

            byte flags1 = _data[baseAddr + 13];
            byte flags2 = _data[baseAddr + 14];
            byte reserved = _data[baseAddr + 15];

            ch.PTTId = (PttIdMode)((flags1 >> 6) & 3);
            ch.FrequencyHop = (flags1 & 0x20) != 0;
            ch.BusyLock = (flags1 & 0x04) != 0;

            ch.Power = (PowerLevel)((flags2 >> 4) & 3);
            ch.Bandwidth = (flags2 & 0x08) != 0 ? ChannelBand.Narrow : ChannelBand.Wide;
            ch.Modulation = (RxModulation)(reserved & 3);
            ch.InScanList = GetBit(SCANINDEX_START, idx);
            return ch;
        }

        /// <summary>
        /// Записывает канал в образ. Обновляет бит-карту валидности (канал валиден,
        /// если RX-частота &gt; 0) и бит-карту списка сканирования.
        /// </summary>
        /// <param name="channel">Запись канала (<see cref="ChannelRecord"/>).</param>
        /// <returns>Возвращает <see langword="this"/>.</returns>
        public TDRadioCodeplug SetChannel(ChannelRecord channel)
        {
            if (channel == null) throw new ArgumentNullException(nameof(channel));
            int idx = RequireChannelIndex(channel.Number);
            int baseAddr = CHANNEL_START + idx * CHANNEL_SIZE;

            byte[] rx = EncodeFrequency(channel.RxFrequencyMHz);
            byte[] tx = channel.TxFrequencyMHz > 0
                ? EncodeFrequency(channel.TxFrequencyMHz)
                : new byte[] { 0xFF, 0xFF, 0xFF, 0xFF };
            byte[] rxt = EncodeTone(channel.RXTone);
            byte[] txt = EncodeTone(channel.TXTone);
            int ptt = (int)channel.PTTId;
            int pw = (int)channel.Power;
            byte flags1 = (byte)((ptt << 6) | (channel.FrequencyHop ? 0x20 : 0) | (channel.BusyLock ? 0x04 : 0));
            byte flags2 = (byte)((pw << 4) | (channel.Bandwidth == ChannelBand.Narrow ? 0x08 : 0));
            byte reserved = (byte)((int)channel.Modulation & 3);

            WriteBytes(baseAddr, rx);
            WriteBytes(baseAddr + 4, tx);
            WriteBytes(baseAddr + 8, rxt);
            WriteBytes(baseAddr + 10, txt);
            _data[baseAddr + 12] = (byte)Clamp(channel.Scrambler, 0, 16);
            _data[baseAddr + 13] = flags1;
            _data[baseAddr + 14] = flags2;
            _data[baseAddr + 15] = reserved;
            EncodeName(channel.Name, CHNAME_START + idx * CHNAME_SIZE, CHNAME_SIZE);

            SetBit(CHINDEX_START, idx, channel.RxFrequencyMHz > 0);
            SetBit(SCANINDEX_START, idx, channel.InScanList);
            return this;
        }

        // ==========================================================================
        //  MR (MEMORY / ПАМЯТЬ) — индексы валидности и списка сканирования
        // ==========================================================================

        /// <summary>Проверяет, является ли канал №<paramref name="number"/> валидным (запрограммированным).</summary>
        /// <param name="number">Номер канала 1..199.</param>
        /// <returns><see langword="true"/>, если бит валидности установлен.</returns>
        public bool IsChannelValid(int number)
        {
            return GetBit(CHINDEX_START, RequireChannelIndex(number));
        }

        /// <summary>
        /// Вручную задаёт бит валидности канала. Обычно бит выставляется автоматически
        /// в <see cref="SetChannel"/>, но метод позволяет снять валидность без очистки данных.
        /// </summary>
        /// <param name="number">Номер канала 1..199.</param>
        /// <param name="valid">Валиден ли канал.</param>
        /// <returns>Возвращает <see langword="this"/>.</returns>
        public TDRadioCodeplug SetChannelValid(int number, bool valid)
        {
            SetBit(CHINDEX_START, RequireChannelIndex(number), valid);
            return this;
        }

        /// <summary>Проверяет, входит ли канал в список сканирования.</summary>
        /// <param name="number">Номер канала 1..199.</param>
        /// <returns><see langword="true"/>, если бит установлен.</returns>
        public bool IsInScanList(int number)
        {
            return GetBit(SCANINDEX_START, RequireChannelIndex(number));
        }

        /// <summary>Добавляет/убирает канал в список сканирования.</summary>
        /// <param name="number">Номер канала 1..199.</param>
        /// <param name="inScan">В списке сканирования или нет.</param>
        /// <returns>Возвращает <see langword="this"/>.</returns>
        public TDRadioCodeplug SetScanList(int number, bool inScan)
        {
            SetBit(SCANINDEX_START, RequireChannelIndex(number), inScan);
            return this;
        }

        // ==========================================================================
        //  VFO A / VFO B
        // ==========================================================================

        /// <summary>Возвращает запись VFO A (смещение 6480).</summary>
        /// <returns>Объект <see cref="VfoRecord"/> с расшифрованными полями.</returns>
        public VfoRecord GetVfoA() { return GetVfo(VFO_A_START, 0); }

        /// <summary>Возвращает запись VFO B (смещение 6496).</summary>
        /// <returns>Объект <see cref="VfoRecord"/>.</returns>
        public VfoRecord GetVfoB() { return GetVfo(VFO_B_START, 4); }

        /// <summary>Записывает VFO A.</summary>
        /// <param name="vfo">Запись VFO.</param>
        public void SetVfoA(VfoRecord vfo) { SetVfo(VFO_A_START, 0, vfo); }

        /// <summary>Записывает VFO B.</summary>
        /// <param name="vfo">Запись VFO.</param>
        public void SetVfoB(VfoRecord vfo) { SetVfo(VFO_B_START, 4, vfo); }

        private VfoRecord GetVfo(int baseAddr, int offsetSlot)
        {
            var v = new VfoRecord
            {
                RxFrequencyMHz = DecodeFrequency(_data, baseAddr + 0),
                TxFrequencyMHz = DecodeFrequency(_data, baseAddr + 4),
                RXTone = DecodeTone(_data, baseAddr + 8),
                TXTone = DecodeTone(_data, baseAddr + 10),
                Scrambler = _data[baseAddr + 12],
                FrequencyOffsetMHz = DecodeOffset(_data, FREQ_OFFSET_START + offsetSlot),
            };
            byte b13 = _data[baseAddr + 13];
            byte b14 = _data[baseAddr + 14];
            byte b15 = _data[baseAddr + 15];
            v.PTTId = (PttIdMode)((b13 >> 6) & 3);
            v.FrequencyHop = (b13 & 0x20) != 0;
            v.BusyLock = (b13 & 0x04) != 0;
            v.ScramblerEnable = (b14 & 0x40) != 0;
            v.Power = (PowerLevel)((b14 >> 4) & 3);
            v.Bandwidth = (b14 & 0x08) != 0 ? ChannelBand.Narrow : ChannelBand.Wide;
            v.OffsetDirection = (FreqOffsetDirection)(b14 & 3);
            v.Modulation = (RxModulation)(b15 & 3);
            return v;
        }

        private void SetVfo(int baseAddr, int offsetSlot, VfoRecord v)
        {
            if (v == null) throw new ArgumentNullException(nameof(v));
            WriteBytes(baseAddr + 0, EncodeFrequency(v.RxFrequencyMHz));
            WriteBytes(baseAddr + 4, v.TxFrequencyMHz > 0 ? EncodeFrequency(v.TxFrequencyMHz) : new byte[] { 0xFF, 0xFF, 0xFF, 0xFF });
            WriteBytes(baseAddr + 8, EncodeTone(v.RXTone));
            WriteBytes(baseAddr + 10, EncodeTone(v.TXTone));
            _data[baseAddr + 12] = (byte)Clamp(v.Scrambler, 0, 16);

            byte b13 = (byte)(((int)v.PTTId << 6) | (v.FrequencyHop ? 0x20 : 0) | (v.BusyLock ? 0x04 : 0));
            byte b14 = (byte)((v.ScramblerEnable ? 0x40 : 0) | ((int)v.Power << 4)
                              | (v.Bandwidth == ChannelBand.Narrow ? 0x08 : 0)
                              | ((int)v.OffsetDirection & 3));
            byte b15 = (byte)((int)v.Modulation & 3);
            _data[baseAddr + 13] = b13;
            _data[baseAddr + 14] = b14;
            _data[baseAddr + 15] = b15;

            // Сдвиг частоты хранится отдельным блоком (3248): [0..3]=VFO A, [4..7]=VFO B.
            WriteBytes(FREQ_OFFSET_START + offsetSlot, EncodeOffset(v.FrequencyOffsetMHz));
        }

        // ==========================================================================
        //  FM RADIO (частоты вещания 76..108 МГц)
        // ==========================================================================

        /// <summary>Возвращает FM-канал (1..25).</summary>
        /// <param name="number">Номер FM-канала 1..25.</param>
        /// <returns>Запись <see cref="FmChannelRecord"/>.</returns>
        public FmChannelRecord GetFmChannel(int number)
        {
            int idx = RequireIndex(number - 1, FM_CHANNEL_COUNT, "FM-канала");
            int baseAddr = FM_CHANNELS_START + idx * 4;
            var rec = new FmChannelRecord
            {
                Number = number,
                FrequencyMHz = DecodeFmFrequency(_data, baseAddr),
                Enabled = GetBit(FM_VALID_START, idx),
            };
            return rec;
        }

        /// <summary>Записывает FM-канал (1..25).</summary>
        /// <param name="channel">Запись FM-канала.</param>
        /// <returns>Возвращает <see langword="this"/>.</returns>
        public TDRadioCodeplug SetFmChannel(FmChannelRecord channel)
        {
            if (channel == null) throw new ArgumentNullException(nameof(channel));
            int idx = RequireIndex(channel.Number - 1, FM_CHANNEL_COUNT, "FM-канала");
            int baseAddr = FM_CHANNELS_START + idx * 4;
            byte[] b = EncodeFmFrequency(channel.FrequencyMHz);
            WriteBytes(baseAddr, b);
            SetBit(FM_VALID_START, idx, channel.Enabled && channel.FrequencyMHz > 0);
            return this;
        }

        /// <summary>Возвращает частоту FM-VFO, МГц.</summary>
        /// <returns>Частота, МГц.</returns>
        public double GetFmVfoFrequencyMHz()
        {
            return DecodeFmFrequency(_data, FM_VFO_START);
        }

        /// <summary>Задаёт частоту FM-VFO, МГц.</summary>
        /// <param name="mhz">Частота 76..108 МГц.</param>
        /// <returns>Возвращает <see langword="this"/>.</returns>
        public TDRadioCodeplug SetFmVfoFrequencyMHz(double mhz)
        {
            WriteBytes(FM_VFO_START, EncodeFmFrequency(mhz));
            return this;
        }

        /// <summary>Режим FM-радио (VFO или канал).</summary>
        /// <param name="mode">Режим.</param>
        public void SetFmMode(FmMode mode)
        {
            SetFmModeBit(mode == FmMode.Channel, FM_SETTINGS_START, 0x80);
        }

        /// <summary>Включён ли мониторинг при FM.</summary>
        /// <param name="enabled">Значение.</param>
        public void SetFmMonitor(bool enabled)
        {
            SetFmModeBit(enabled, FM_SETTINGS_START, 0x08);
        }

        /// <summary>Текущий активный FM-канал (1..25).</summary>
        /// <param name="channel">Номер 1..25.</param>
        /// <returns>Возвращает <see langword="this"/>.</returns>
        public TDRadioCodeplug SetFmCurrentChannel(int channel)
        {
            int c = Clamp(channel, 1, FM_CHANNEL_COUNT);
            _data[FM_CURRENT_CHANNEL_START] = (byte)c;
            return this;
        }

        private void SetFmModeBit(bool on, int offset, byte mask)
        {
            byte b = _data[offset];
            if (on) b |= mask; else b &= (byte)~mask;
            _data[offset] = b;
        }

        // ==========================================================================
        //  ОБЩИЕ НАСТРОЙКИ
        // ==========================================================================

        /// <summary>Возвращает загрузочное сообщение bootMsg (1..3).</summary>
        /// <param name="index">1..3 (bootMsg1..3).</param>
        /// <returns>Текст сообщения (до 16 символов).</returns>
        public string GetBootMessage(int index)
        {
            int offset = BOOT_MSG1_START + (RequireIndex(index - 1, 3, "bootMsg") * BOOT_MSG_LEN);
            return DecodeAscii(_data, offset, BOOT_MSG_LEN);
        }

        /// <summary>Устанавливает загрузочное сообщение bootMsg (1..3).</summary>
        /// <param name="index">1..3.</param>
        /// <param name="text">Текст до 16 печатных ASCII-символов.</param>
        /// <returns>Возвращает <see langword="this"/>.</returns>
        public TDRadioCodeplug SetBootMessage(int index, string text)
        {
            int offset = BOOT_MSG1_START + (RequireIndex(index - 1, 3, "bootMsg") * BOOT_MSG_LEN);
            WriteAsciiPadded(text, offset, BOOT_MSG_LEN);
            return this;
        }

        /// <summary>Микрофонное усиление (0..32).</summary>
        /// <param name="value">Значение 0..32.</param>
        public void SetMicGain(int value)
        {
            SetClampedByte(MIC_GAIN_START, value, 0, 32);
        }

        /// <summary>Микрофонное усиление (0..32).</summary>
        /// <returns>Значение 0..32.</returns>
        public int GetMicGain()
        {
            return _data[MIC_GAIN_START];
        }

        /// <summary>Код языка (индекс из списка).</summary>
        /// <param name="value">0..255.</param>
        public void SetLanguage(byte value) { _data[LANGUAGE_SELECT_START] = value; }

        /// <summary>Код языка.</summary>
        /// <returns>Индекс языка.</returns>
        public byte GetLanguage() { return _data[LANGUAGE_SELECT_START]; }

        /// <summary>Стиль дисплея.</summary>
        /// <param name="value">0..255.</param>
        public void SetDisplayStyle(byte value) { _data[DISPLAY_STYLE_START] = value; }

        /// <summary>Стиль дисплея.</summary>
        /// <returns>Индекс стиля.</returns>
        public byte GetDisplayStyle() { return _data[DISPLAY_STYLE_START]; }

        /// <summary>Цвет меню.</summary>
        /// <param name="value">0..255.</param>
        public void SetMenuColor(byte value) { _data[MENU_COLOR_START] = value; }

        /// <summary>Цвет меню.</summary>
        /// <returns>Индекс цвета.</returns>
        public byte GetMenuColor() { return _data[MENU_COLOR_START]; }

        /// <summary>Верхний предел сканирования VFO (1..999).</summary>
        /// <param name="value">1..999.</param>
        public void SetVfoScanUpperLimit(int value)
        {
            WriteUInt16LE(VFO_SCAN_UPPER_START, (ushort)Clamp(value, 1, 999));
        }

        /// <summary>Верхний предел сканирования VFO.</summary>
        /// <returns>1..999.</returns>
        public int GetVfoScanUpperLimit()
        {
            return ReadUInt16LE(VFO_SCAN_UPPER_START);
        }

        /// <summary>Нижний предел сканирования VFO (1..999).</summary>
        /// <param name="value">1..999.</param>
        public void SetVfoScanLowerLimit(int value)
        {
            WriteUInt16LE(VFO_SCAN_LOWER_START, (ushort)Clamp(value, 1, 999));
        }

        /// <summary>Нижний предел сканирования VFO.</summary>
        /// <returns>1..999.</returns>
        public int GetVfoScanLowerLimit()
        {
            return ReadUInt16LE(VFO_SCAN_LOWER_START);
        }

        /// <summary>Время зависания скана (индекс списка).</summary>
        /// <param name="value">0..255.</param>
        public void SetScanHangTime(byte value) { _data[SCAN_HANG_TIME_START] = value; }

        /// <summary>Время зависания скана.</summary>
        /// <returns>Индекс.</returns>
        public byte GetScanHangTime() { return _data[SCAN_HANG_TIME_START]; }

        // ==========================================================================
        //  DTMF
        // ==========================================================================

        /// <summary>Возвращает DTMF-код по имени поля.</summary>
        /// <param name="field">Имя поля: "stun", "kill", "start", "end".</param>
        /// <returns>Строка кода (max 8 символов).</returns>
        public string GetDtmfCode(string field)
        {
            int offset = GetDtmfOffset(field, out bool withLength);
            return DecodeDtmf(_data, offset, withLength);
        }

        /// <summary>Устанавливает DTMF-код по имени поля.</summary>
        /// <param name="field">Имя поля: "stun", "kill", "start", "end".</param>
        /// <param name="code">Строка кода (max 8 символов, цифры 0-9, A-D, *, #).</param>
        /// <returns>Возвращает <see langword="this"/>.</returns>
        public TDRadioCodeplug SetDtmfCode(string field, string code)
        {
            int offset = GetDtmfOffset(field, out bool withLength);
            EncodeDtmf(code, _data, offset, withLength);
            return this;
        }

        /// <summary>Локальный DTMF ID (до 3 знаков).</summary>
        /// <param name="code">Код до 3 символов.</param>
        public void SetDtmfLocalId(string code)
        {
            EncodeDtmfSimple(code, _data, DTMF_LOCAL_ID_START, 3);
        }

        /// <summary>Локальный DTMF ID (до 3 знаков).</summary>
        /// <returns>Строка кода.</returns>
        public string GetDtmfLocalId()
        {
            return DecodeDtmfSimple(_data, DTMF_LOCAL_ID_START, 3);
        }

        /// <summary>Кодовая группа DTMF (1..8).</summary>
        /// <param name="group">1..8.</param>
        /// <returns>Строка кода.</returns>
        public string GetDtmfCodeGroup(int group)
        {
            int offset = DTMF_CODE_GROUP1_START + (RequireIndex(group - 1, 8, "DTMF-группы") * 16);
            return DecodeDtmfSimple(_data, offset, 16);
        }

        /// <summary>Задаёт кодовую группу DTMF (1..8).</summary>
        /// <param name="group">1..8.</param>
        /// <param name="code">Код до 16 символов.</param>
        /// <returns>Возвращает <see langword="this"/>.</returns>
        public TDRadioCodeplug SetDtmfCodeGroup(int group, string code)
        {
            int offset = DTMF_CODE_GROUP1_START + (RequireIndex(group - 1, 8, "DTMF-группы") * 16);
            EncodeDtmfSimple(code, _data, offset, 16);
            return this;
        }

        // ==========================================================================
        //  CSV
        // ==========================================================================

        private static readonly string[] CsvHeader =
        {
            "Channel No", "RX Freq [MHz]", "TX Freq [MHz]", "RX CTCSS/DCS", "TX CTCSS/DCS",
            "Power", "Bandwidth", "Scrambler", "PTT ID", "Freq Hop", "Busy Lock",
            "Scan", "Rx Modulation", "Channel Name",
        };

        /// <summary>Псевдонимы имён колонок CSV (индекс = позиция в <see cref="CsvHeader"/>).</summary>
        private static readonly string[][] CsvAliases =
        {
            new[] { "channel no", "channel", "ch", "location", "#", "no" },                       // Channel No
            new[] { "rx freq", "rx", "rx frequency", "receive frequency" },                       // RX Freq
            new[] { "tx freq", "tx", "tx frequency", "transmit frequency" },                      // TX Freq
            new[] { "rx ctcss", "rx ctcss/dcs", "rx tone", "rx subaudio" },                       // RX CTCSS/DCS
            new[] { "tx ctcss", "tx ctcss/dcs", "tx tone", "tx subaudio" },                       // TX CTCSS/DCS
            new[] { "power", "lmh", "power level", "output power", "sila" },                      // Power
            new[] { "bandwidth", "band width", "band" },                                          // Bandwidth
            new[] { "scrambler", "scramble", "scrambling" },                                      // Scrambler
            new[] { "ptt id", "pttid", "ptt" },                                                   // PTT ID
            new[] { "freq hop", "frequency hop", "hop" },                                         // Freq Hop
            new[] { "busy lock", "busy" },                                                        // Busy Lock
            new[] { "scan", "scan add", "scanlist", "scanning" },                                 // Scan
            new[] { "rx modulation", "rx model", "modulation", "rx mode" },                       // Rx Modulation
            new[] { "channel name", "name", "display", "display name", "shortcut", "alias" },     // Channel Name
        };

        /// <summary>
        /// Экспортирует запрограммированные каналы (RX-частота &gt; 0) в CSV-файл
        /// в формате нашего прямого скрипта <c>td_to_csv.py</c>. CSV пишется с BOM (UTF-8).
        /// </summary>
        /// <param name="path">Путь к выходному CSV.</param>
        /// <returns>Количество записанных каналов.</returns>
        public int ExportToCSV(string path)
        {
            if (path == null) throw new ArgumentNullException(nameof(path));
            var sb = new StringBuilder();
            sb.Append(string.Join(CSVDelimiter, CsvHeader)).Append("\r\n");
            int count = 0;
            for (int n = 1; n <= CHANNEL_COUNT; n++)
            {
                ChannelRecord c = GetChannel(n);
                if (c.RxFrequencyMHz <= 0) continue;
                string tx = c.TxFrequencyMHz > 0 ? FormatFreq(c.TxFrequencyMHz) : "";
                sb.Append(n).Append(CSVDelimiter)
                  .Append(FormatFreq(c.RxFrequencyMHz)).Append(CSVDelimiter)
                  .Append(tx).Append(CSVDelimiter)
                  .Append(c.RXTone).Append(CSVDelimiter)
                  .Append(c.TXTone).Append(CSVDelimiter)
                  .Append(PowerToStr(c.Power)).Append(CSVDelimiter)
                  .Append(c.Bandwidth == ChannelBand.Narrow ? "Narrow" : "Wide").Append(CSVDelimiter)
                  .Append(c.Scrambler).Append(CSVDelimiter)
                  .Append(PttToStr(c.PTTId)).Append(CSVDelimiter)
                  .Append(c.FrequencyHop ? "On" : "Off").Append(CSVDelimiter)
                  .Append(c.BusyLock ? "On" : "Off").Append(CSVDelimiter)
                  .Append(c.InScanList ? "Yes" : "No").Append(CSVDelimiter)
                  .Append(c.Modulation == RxModulation.AM ? "AM" : "FM").Append(CSVDelimiter)
                  .Append(c.Name)
                  .Append("\r\n");
                count++;
            }
            File.WriteAllText(path, sb.ToString(), new UTF8Encoding(true));
            return count;
        }

        /// <summary>
        /// Импортирует каналы из CSV, создавая новый пустой кодплаг (<see cref="NewFile"/>).
        /// Поддерживается формат нашего <c>td_to_csv.py</c>, а также псевдонимы колонок
        /// (например <c>LMH</c> для Power, <c>Display</c>/<c>Shortcut</c> для имени,
        /// <c>#</c>/<c>RX</c>/<c>TX</c> для номера/частот). Требуется колонка RX-частоты;
        /// ненайденные необязательные колонки берут значения по умолчанию.
        /// </summary>
        /// <param name="path">Путь к CSV.</param>
        /// <returns>Количество импортированных каналов.</returns>
        /// <exception cref="InvalidDataException">CSV не содержит обязательной колонки RX-частоты.</exception>
        public int ImportFromCSV(string path)
        {
            NewFile();
            return ImportCsvCore(path, replaceNumbers: true);
        }

        /// <summary>
        /// Обновляет каналы в существующем образе данными из CSV (патч). Каналы,
        /// номера которых есть в CSV, перезаписываются; остальные не трогаются.
        /// </summary>
        /// <param name="path">Путь к CSV.</param>
        /// <returns>Количество обновлённых каналов.</returns>
        public int UpdateFromCSV(string path)
        {
            return ImportCsvCore(path, replaceNumbers: true);
        }

        private int ImportCsvCore(string path, bool replaceNumbers)
        {
            if (path == null) throw new ArgumentNullException(nameof(path));
            if (!File.Exists(path)) throw new FileNotFoundException("Файл не найден", path);

            string[] lines = File.ReadAllLines(path, Encoding.UTF8);
            if (lines.Length == 0)
                throw new InvalidDataException("Пустой CSV-файл.");

            string[] header = SplitCsvLine(lines[0]);
            int[] map = new int[CsvHeader.Length];
            for (int i = 0; i < map.Length; i++) map[i] = -1;
            for (int i = 0; i < CsvHeader.Length; i++)
                map[i] = FindColumn(header, CsvAliases[i]);

            int rxCol = FindColumn(header, "rx freq", "rx", "rx frequency", "receive frequency");
            if (rxCol < 0) throw new InvalidDataException("CSV не содержит колонку RX-частоты.");

            int count = 0;
            for (int line = 1; line < lines.Length; line++)
            {
                if (string.IsNullOrWhiteSpace(lines[line])) continue;
                string[] f = SplitCsvLine(lines[line]);
                int n = Value(f, map[0]) is string s && int.TryParse(s, out int nn) ? nn : (replaceNumbers ? count + 1 : 0);
                if (n < 1 || n > CHANNEL_COUNT) { count++; continue; }

                var c = new ChannelRecord
                {
                    Number = n,
                    RxFrequencyMHz = ParseFreq(Value(f, rxCol)),
                };
                if (c.RxFrequencyMHz <= 0) { count++; continue; }
                c.TxFrequencyMHz = ParseFreq(Text(f, map[2]));
                c.RXTone = Text(f, map[3]);
                c.TXTone = Text(f, map[4]);
                c.Power = ParsePower(Text(f, map[5]));
                c.Bandwidth = Text(f, map[6]).Trim().Equals("Narrow", StringComparison.OrdinalIgnoreCase)
                    ? ChannelBand.Narrow : ChannelBand.Wide;
                c.Scrambler = ParseInt(Text(f, map[7]), 0);
                c.PTTId = ParsePtt(Text(f, map[8]));
                c.FrequencyHop = IsOn(Text(f, map[9]));
                c.BusyLock = IsOn(Text(f, map[10]));
                c.InScanList = IsYes(Text(f, map[11]));
                c.Modulation = Text(f, map[12]).Trim().Equals("AM", StringComparison.OrdinalIgnoreCase)
                    ? RxModulation.AM : RxModulation.FM;
                c.Name = Text(f, map[13]);
                SetChannel(c);
                count++;
            }
            return count;
        }

        // ==========================================================================
        //  ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ (КОДИРОВАНИЕ/ДЕКОДИРОВАНИЕ)
        // ==========================================================================

        private static bool IsAllFF(byte[] b, int off, int len)
        {
            for (int i = off; i < off + len; i++) if (b[i] != 0xFF) return false;
            return true;
        }

        private static bool IsEqual(byte[] b, int off, byte[] pattern)
        {
            if (off + pattern.Length > b.Length) return false;
            for (int i = 0; i < pattern.Length; i++) if (b[off + i] != pattern[i]) return false;
            return true;
        }

        private static byte[] EncodeFrequency(double mhz)
        {
            if (mhz <= 0 || mhz > 999.99999) throw new ArgumentOutOfRangeException(nameof(mhz),
                string.Format("Частота {0} МГц вне диапазона (0<x<=999.99999).", mhz));
            long val = (long)Math.Round(mhz * 100000.0);
            if (val <= 0 || val > 99999999) throw new ArgumentOutOfRangeException(nameof(mhz));
            var b = new byte[4];
            for (int i = 0; i < 4; i++)
            {
                long pair = val % 100; val /= 100;
                b[i] = (byte)(((pair / 10) << 4) | (pair % 10));
            }
            return b;
        }

        private static double DecodeFrequency(byte[] data, int off)
        {
            bool empty = true;
            for (int i = 0; i < 4; i++) if (data[off + i] != 0x00 && data[off + i] != 0xFF) { empty = false; break; }
            if (empty) return 0;
            long val = 0; long mul = 1;
            for (int i = 0; i < 4; i++)
            {
                int hi = data[off + i] >> 4, lo = data[off + i] & 0xF;
                if (hi > 9 || lo > 9) return 0;
                val += (hi * 10L + lo) * mul;
                mul *= 100;
            }
            if (val <= 0) return 0;
            return val / 100000.0;
        }

        private static byte[] EncodeTone(string s)
        {
            s = (s ?? "").Trim().ToUpperInvariant();
            if (s.Length == 0 || s == "OFF") return new byte[] { 0xFF, 0xFF };
            if (s[0] == 'D')
            {
                string digits = "";
                foreach (char c in s) if (char.IsDigit(c)) digits += c;
                if (digits.Length != 3) return new byte[] { 0xFF, 0xFF };
                int h = digits[0] - '0', t = digits[1] - '0', u = digits[2] - '0';
                if (h > 7 || t > 7 || u > 7) return new byte[] { 0xFF, 0xFF };
                bool inv = s.EndsWith("I", StringComparison.Ordinal);
                return new byte[] { (byte)((t << 4) | u), (byte)((inv ? 0xC : 0x8) << 4 | h) };
            }
            // CTCSS
            double freq;
            if (!double.TryParse(s.Replace(",", "."), NumberStyles.Float, CultureInfo.InvariantCulture, out freq)) freq = -1;
            int code = (int)Math.Round(freq * 10);
            if (code < 670 || code > 2541) return new byte[] { 0xFF, 0xFF };
            string p = code.ToString("D4");
            return new byte[] { (byte)HexByte(p.Substring(2, 2)), (byte)HexByte(p.Substring(0, 2)) };
        }

        private static string DecodeTone(byte[] data, int off)
        {
            byte b0 = data[off], b1 = data[off + 1];
            if (b0 == 0x00 || b0 == 0xFF || b1 == 0x00 || b1 == 0xFF) return "OFF";
            int pol = b1 >> 4;
            if (pol >= 8)
            {
                int hundreds = b1 & 0xF;
                int tens = b0 >> 4;
                int units = b0 & 0xF;
                return string.Format("D{0}{1}{2}{3}", hundreds, tens, units, pol == 0xC ? "I" : "N");
            }
            string hex = b1.ToString("X2") + b0.ToString("X2");
            foreach (char c in hex) if (!char.IsDigit(c)) return "OFF";
            int value = int.Parse(hex, CultureInfo.InvariantCulture);
            return (value / 10.0).ToString("0.0", CultureInfo.InvariantCulture);
        }

        private static byte[] EncodeOffset(double mhz)
        {
            if (mhz <= 0) return new byte[] { 0, 0, 0, 0 };
            long val = (long)Math.Round(mhz * 100000.0);
            if (val <= 0 || val > 999999) return new byte[] { 0, 0, 0, 0 };
            var b = new byte[4];
            for (int i = 0; i < 4; i++)
            {
                long pair = val % 100; val /= 100;
                b[i] = (byte)(((pair / 10) << 4) | (pair % 10));
            }
            return b;
        }

        private static double DecodeOffset(byte[] data, int off)
        {
            long val = 0; long mul = 1;
            for (int i = 0; i < 4; i++)
            {
                int hi = data[off + i] >> 4, lo = data[off + i] & 0xF;
                if (hi > 9 || lo > 9) return 0;
                val += (hi * 10L + lo) * mul;
                mul *= 100;
            }
            if (val <= 0) return 0;
            return val / 100000.0;
        }

        private static byte[] EncodeFmFrequency(double mhz)
        {
            if (mhz <= 0) return new byte[] { 0, 0, 0, 0 };
            if (mhz < 76.0 || mhz > 108.0) throw new ArgumentOutOfRangeException(nameof(mhz), "FM-частота должна быть 76..108 МГц.");
            int num = (int)Math.Round(mhz * 10);
            return new byte[]
            {
                (byte)(((num / 10 % 10) << 4) | (num % 10)),
                (byte)(((num / 1000 % 10) << 4) | (num / 100 % 10)),
                0, 0,
            };
        }

        private static double DecodeFmFrequency(byte[] data, int off)
        {
            if (data[off] == 0 && data[off + 1] == 0) return 0;
            int num = ((data[off + 1] >> 4) * 1000) + ((data[off + 1] & 0xF) * 100)
                    + ((data[off] >> 4) * 10) + (data[off] & 0xF);
            double mhz = num / 10.0;
            return (mhz >= 76.0 && mhz <= 108.0) ? mhz : (mhz <= 0 ? 0 : 76.0);
        }

        private void EncodeName(string name, int offset, int length)
        {
            byte[] raw = EncodeGb2312(name ?? "");
            for (int i = 0; i < length; i++)
                _data[offset + i] = i < raw.Length ? raw[i] : (byte)0xFF;
        }

        private string DecodeName(int offset)
        {
            var buf = new byte[CHNAME_SIZE];
            Array.Copy(_data, offset, buf, 0, CHNAME_SIZE);
            return DecodeGb2312Terminated(buf);
        }

        private string DecodeAscii(byte[] data, int offset, int length)
        {
            var sb = new StringBuilder();
            for (int i = 0; i < length; i++)
            {
                byte c = data[offset + i];
                if (c == 0x00 || c == 0xFF) break;
                sb.Append((char)c);
            }
            return sb.ToString();
        }

        private void WriteAsciiPadded(string text, int offset, int length)
        {
            for (int i = 0; i < length; i++) _data[offset + i] = 0x00;
            if (string.IsNullOrEmpty(text)) return;
            var sb = new StringBuilder();
            foreach (char c in text) if (c >= 0x20 && c <= 0x7E) sb.Append(c);
            string s = sb.ToString();
            if (s.Length > length) s = s.Substring(0, length);
            for (int i = 0; i < s.Length; i++) _data[offset + i] = (byte)s[i];
        }

        private void EncodeDtmf(string code, byte[] data, int offset, bool withLength)
        {
            for (int i = offset; i < offset + 16; i++) data[i] = 0xFF;
            string c = (code ?? "").Trim();
            if (c.Length > 8) c = c.Substring(0, 8);
            for (int i = 0; i < c.Length; i++) data[offset + i] = (byte)DtmfValue(c[i]);
            if (withLength) data[offset + 15] = (byte)c.Length;
        }

        private string DecodeDtmf(byte[] data, int offset, bool withLength)
        {
            int len;
            if (withLength)
            {
                len = data[offset + 15];
                if (len == 255 || len > 8) len = 8;
            }
            else len = 8;
            var sb = new StringBuilder();
            for (int i = 0; i < len; i++)
            {
                int v = data[offset + i];
                if (v == 0xFF || v == 0x00) break;
                sb.Append(DtmfChar(v));
            }
            return sb.ToString();
        }

        private void EncodeDtmfSimple(string code, byte[] data, int offset, int length)
        {
            for (int i = 0; i < length; i++) data[offset + i] = 0xFF;
            string c = (code ?? "").Trim();
            if (c.Length > length) c = c.Substring(0, length);
            for (int i = 0; i < c.Length; i++) data[offset + i] = (byte)DtmfValue(c[i]);
        }

        private string DecodeDtmfSimple(byte[] data, int offset, int length)
        {
            var sb = new StringBuilder();
            for (int i = 0; i < length; i++)
            {
                int v = data[offset + i];
                if (v == 0xFF || v == 0x00) break;
                sb.Append(DtmfChar(v));
            }
            return sb.ToString();
        }

        private int GetDtmfOffset(string field, out bool withLength)
        {
            field = (field ?? "").ToLowerInvariant();
            switch (field)
            {
                case "stun": withLength = true; return DTMF_STUN_START;
                case "kill": withLength = true; return DTMF_KILL_START;
                case "start": withLength = true; return DTMF_START_CODE_START;
                case "end": withLength = true; return DTMF_END_CODE_START;
                default:
                    throw new ArgumentOutOfRangeException(nameof(field),
                        "Поле должно быть 'stun', 'kill', 'start' или 'end'. Локальный ID/группы — отдельными методами.");
            }
        }

        private void SetClampedByte(int offset, int value, int min, int max)
        {
            _data[offset] = (byte)Clamp(value, min, max);
        }

        private void WriteUInt16LE(int offset, ushort value)
        {
            _data[offset] = (byte)(value & 0xFF);
            _data[offset + 1] = (byte)((value >> 8) & 0xFF);
        }

        private ushort ReadUInt16LE(int offset)
        {
            return (ushort)(_data[offset] | (_data[offset + 1] << 8));
        }

        private bool GetBit(int blockStart, int bitIndex)
        {
            int byteIdx = blockStart + bitIndex / 8;
            return (_data[byteIdx] & (1 << (bitIndex % 8))) != 0;
        }

        private void SetBit(int blockStart, int bitIndex, bool on)
        {
            int byteIdx = blockStart + bitIndex / 8;
            int mask = 1 << (bitIndex % 8);
            if (on) _data[byteIdx] |= (byte)mask;
            else _data[byteIdx] &= (byte)~mask;
        }

        private void ValidateOffset(int offset, int length)
        {
            if (offset < 0 || offset + length > EEROM_SPACE)
                throw new ArgumentOutOfRangeException(nameof(offset),
                    string.Format("Смещение {0} (длина {1}) вне границ образа 0..{2}.", offset, length, EEROM_SPACE));
        }

        private int RequireChannelIndex(int number)
        {
            if (number < 1 || number > CHANNEL_COUNT)
                throw new ArgumentOutOfRangeException(nameof(number),
                    string.Format("Номер канала должен быть 1..{0}.", CHANNEL_COUNT));
            return number - 1;
        }

        private int RequireIndex(int value, int count, string what)
        {
            if (value < 0 || value >= count)
                throw new ArgumentOutOfRangeException(nameof(value),
                    string.Format("Индекс {0} вне диапазона 0..{1}.", what, count - 1));
            return value;
        }

        private static int Clamp(int value, int min, int max)
        {
            return value < min ? min : (value > max ? max : value);
        }

        private static int HexByte(string two)
        {
            return int.Parse(two, NumberStyles.HexNumber, CultureInfo.InvariantCulture);
        }

        private static int DtmfValue(char c)
        {
            if (c >= '0' && c <= '9') return c - '0';
            switch (c)
            {
                case 'A': return 10;
                case 'B': return 11;
                case 'C': return 12;
                case 'D': return 13;
                case '*': return 14;
                case '#': return 15;
            }
            throw new ArgumentOutOfRangeException(nameof(c), "Некорректный DTMF-символ: " + c);
        }

        private static char DtmfChar(int v)
        {
            switch (v)
            {
                case 0: return '0'; case 1: return '1'; case 2: return '2'; case 3: return '3';
                case 4: return '4'; case 5: return '5'; case 6: return '6'; case 7: return '7';
                case 8: return '8'; case 9: return '9';
                case 10: return 'A'; case 11: return 'B'; case 12: return 'C'; case 13: return 'D';
                case 14: return '*'; case 15: return '#';
            }
            return '?';
        }

        // --- кодирование/декодирование GB2312 (имя канала) ---
        // Регистрация провайдера кодовых страниц выполняется через рефлексию, чтобы класс
        // собирался без явной ссылки на пакет System.Text.Encoding.CodePages. Если провайдер
        // недоступен в рантайме, используется UTF-8 (резерв).

        private static Encoding _gb;

        private static Encoding GetGb()
        {
            if (_gb != null) return _gb;
            try
            {
                Type providerType = Type.GetType(
                    "System.Text.CodePagesEncodingProvider, System.Text.Encoding.CodePages");
                if (providerType != null)
                {
                    var instance = providerType.GetProperty("Instance",
                        System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static)
                        .GetValue(null);
                    Encoding.RegisterProvider((EncodingProvider)instance);
                }
            }
            catch (Exception)
            {
                // провайдер недоступен — останется резерв
            }
            try
            {
                _gb = Encoding.GetEncoding("gb2312");
            }
            catch (Exception)
            {
                _gb = Encoding.UTF8; // резерв
            }
            return _gb;
        }

        private static byte[] EncodeGb2312(string text)
        {
            return GetGb().GetBytes(text);
        }

        private static string DecodeGb2312Terminated(byte[] buf)
        {
            int end = buf.Length;
            for (int i = 0; i < buf.Length; i++)
                if (buf[i] == 0x00 || buf[i] == 0xFF) { end = i; break; }
            return GetGb().GetString(buf, 0, end);
        }

        // --- помощники для CSV ---

        private static string Value(string[] f, int col)
        {
            return (col >= 0 && col < f.Length) ? (f[col] ?? "") : "";
        }

        private string Text(string[] f, int col)
        {
            return Value(f, col);
        }

        private static double ParseFreq(string s)
        {
            if (string.IsNullOrWhiteSpace(s)) return 0;
            double d;
            return double.TryParse(s.Trim().Replace(",", "."), NumberStyles.Float, CultureInfo.InvariantCulture, out d) ? d : 0;
        }

        private static int ParseInt(string s, int def)
        {
            return int.TryParse(s.Trim(), out int v) ? v : def;
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

        private static bool IsOn(string s) { return s.Trim().Equals("On", StringComparison.OrdinalIgnoreCase) || s.Trim().Equals("Yes", StringComparison.OrdinalIgnoreCase); }
        private static bool IsYes(string s) { return s.Trim().Equals("Yes", StringComparison.OrdinalIgnoreCase) || s.Trim().Equals("On", StringComparison.OrdinalIgnoreCase); }

        private static string PowerToStr(PowerLevel p)
        {
            switch (p) { case PowerLevel.Low: return "Low"; case PowerLevel.Mid: return "Mid"; default: return "High"; }
        }

        private static string PttToStr(PttIdMode p)
        {
            switch (p) { case PttIdMode.Begin: return "Begin"; case PttIdMode.End: return "End"; case PttIdMode.Both: return "Both"; default: return "Off"; }
        }

        private static string FormatFreq(double mhz)
        {
            return mhz.ToString("0.00000", CultureInfo.InvariantCulture);
        }

        private static int FindColumn(string[] header, params string[] names)
        {
            if (header == null) return -1;
            string[] norm = new string[header.Length];
            for (int i = 0; i < header.Length; i++) norm[i] = Normalize(header[i]);
            for (int exact = 1; exact >= 0; exact--)
                foreach (string a in names)
                {
                    string key = Normalize(a);
                    for (int i = 0; i < norm.Length; i++)
                        if ((exact == 1 && norm[i] == key) || (exact == 0 && norm[i].Contains(key))) return i;
                }
            return -1;
        }

        private static string Normalize(string s)
        {
            return (s ?? "").Trim().ToLowerInvariant();
        }

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