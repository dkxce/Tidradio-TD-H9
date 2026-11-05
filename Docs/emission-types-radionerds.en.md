# Types of radiation (Emission Types)

> Excerpt from ITU Radio Regulations: The basic rules of classification are laid down in Article 2 (Article 2) and detailed in Annex 1 (Appendix 1) to the Regulation.[R-REG-RR-2024](https://www.itu.int/pub/R-REG-RR-2024)

## Background

Emission designator is a seven-character “word” that describes the bandwidth, the type of modulation, the nature of the signal and the type of information transmitted for a particular radio station. The indication of the radiation designation is required in most applications filed with the FCC or Roskomnadzor.

The designation of radiation consists of seven symbols as follows:

* The first four characters define**bandwidth**the bandwidth required to transmit the necessary information with the necessary speed and quality for the system used;
* fifth character defines**modulation**primary carrier;
* The sixth character**character**(a) modulating (their) main carrier;
* the seventh character**type of information transmitted**.

## Strip width required - the first four characters

The required bandwidth is expressed in three digits and one letter. The letter occupies the position of the decimal point and denotes the unit of measurement of the width of the band. The first character cannot be zero, K, M, or G, but must be a non-zero digit or the letter H. The required bandwidth shall be rounded to three significant figures. The rounded value should correspond to the following syntax:

* from 0.00100 to 999 Hz – expressed in Hz (letter H);
* from 1.00 to 999 kHz – expressed in kHz (letter K);
* from 1.00 to 999 MHz – expressed in MHz (letter M);
* 1.00 to 999 GHz is expressed in GHz (the letter G).

## Types of modulation (fifth character)

| Description | The symbol |
| --- | --- |
| Radiation of non-modulated carrier | N |
| Radiation in which the main carrier is modulated in amplitude (including cases where the subcarriers are modulated in an angle): |  |
| - Two-band (with two side stripes) | A |
| Single-lane, full-carrying | H |
| Single-band, with a reduced or variable carrier | R |
| Single-band, with a depressed carrier | J |
| - with independent side stripes | B |
| - with a partially suppressed (residual) side strip | C |
| Radiation in which the main carrier is modulated at an angle: |  |
| Frequency modulation (FM) | F |
| phase modulation (FM) | G |
| Radiation in which the main carrier is modulated in amplitude and angle - simultaneously or in a predetermined sequence | D |
| Pulse radiation (see note below): |  |
| sequence of unmodulated pulses | P |
| Pulse sequence: |  |
| - modulated by amplitude | K |
| Modulated in width/duration | L |
| - modulated by position/phase | M |
| - with angular modulation of the carrier during the pulse period | Q |
| - representing a combination of the above species or created by other means | V |
| Cases not covered above: radiation consists of a main carrier modulated simultaneously or in a predetermined sequence by a combination of two or more of the following types of modulation: amplitude, angular, pulsed | W |
| Cases not covered above | X |

**Note.**If frequency modulation "F" is specified, phase modulation "G" is also considered acceptable. Radiations in which the main carrier is modulated directly by a signal encoded in a quantized form (e.g., pulse code modulation) should be designated as related to amplitude or angular modulation.

## The nature of the modulating signal (sixth character)

| Code. | Description |
| --- | --- |
| 0 | Absence of modulating signal |
| 1 | One channel containing quantized or digital information without using a modulating subcarrier |
| 2 | One channel containing quantized or digital information using a modulating subcarrier |
| 3 | One channel containing analog information |
| 7 | Two or more channels containing quantized or digital information |
| 8 | Two or more channels containing analog information |
| 9 | Combined system: one or more channels of quantized or digital information together with one or more channels of analog information |
| W | Cases not covered above: radiation consists of a main carrier modulated simultaneously or in a predetermined sequence by a combination of two or more types: amplitude, angular, pulse modulation |
| X | Cases not covered above |

## Type of information transmitted (seventh character)

| Code. | Description |
| --- | --- |
| N | No information is transmitted. |
| A | Telegraphy for auditory reception (for example, Morse code) |
| B | Telegraphy for automatic reception (for example, RTTY, radioteletype) |
| C | facsimile |
| D | Data, telemetry, telecontrol |
| E | Telephony (including sound radio broadcasting) |
| F | Television (video) |
| G | A combination of two or more of the above types |
| W | Cases not covered above: combination of two or more types not mentioned above |
| X | Cases not covered above |

## Examples of radiation designations (Designator / Description)

| Designation | Description |
| --- | --- |
| 60H0J2B | PSK31 |
| 100HN0N | Speed radar - 10525 MHz, X-band; 24150 MHz, Ka-band |
| 150HA1A | Continuous wave telegraphy (CW, manual reception of Morse code) |
| 500HJ2D | MT63-500, 50 words/min |
| 1K00J2D | MT63-1000, 100 words/min |
| 2K00J2D | MT63-2000, 200 words/min |
| 2K80J2B | KV radioteletype (RTTY) |
| 2K80J2D | KV PACTOR III |
| 2K80J3E | Analog voice with amplitude modulation (AM), single-band modulation with suppressed carrier (USB or LSB, not simultaneously) |
| 3K00H2B | KV ALE (automatic communication) MIL-STD-188-141A / FED-STD-1045 |
| 3K30F1D | SCADA channel 6.25 kHz (CalAmp Viper SC – 173 MHz) |
| 4K00F1D | NXDN 6.25 kHz, data (IDAS, NEXEDGE) |
| 4K00F1E | NXDN 6.25 kHz, digital voice (IDAS, NEXEDGE) |
| 4K00F1W | NXDN 6.25 kHz, digital voice and data (IDAS, NEXEDGE) |
| 4K00F2D | NXDN 6.25 kHz, CW analog FM identification (IDAS, NEXEDGE) |
| 4K00J1D | Single-band amplitude companding (ACSB; pilot tone/carrier) |
| 4K00J2D | Single-band amplitude companding (ACSB; pilot tone/carrier) |
| 4K00J3E | Voice in single band modulation with amplitude companding (ACSB) |
| 5K60F2D | SCADA |
| 5K76G1E | P25 CQPSK, voice (usually in simulcast systems is NOT P25 Phase II) |
| 6K00A3E | Analog voice with AM, two side bands and full carrier |
| 6K00F1D | SCADA, Frequency Carrier Manipulation (FSK) |
| 6K00F2D | SCADA, Tonal Frequency Manipulation (AFSK) |
| 6K00F3D | SCADA, analog data other than AFSK (variable tone, DTMF, etc.) |
| 7K60FXD | DMR 2 slot (Motorola MOTOTRBO), TDMA data |
| 7K60FXE | DMR 2 slot (Motorola MOTOTRBO), voice TDMA |
| 8K10F1D | P25 Phase I, C4FM data |
| 8K10F1E | P25 Phase I, voice C4FM |
| 8K10F1W | P25 Phase II, Subscriber Devices (H-CPM) |
| 8K30F1D | NXDN 12.5 kHz, data (Wide IDAS, NEXEDGE) |
| 8K30F1E | NXDN 12.5 kHz, digital voice (Wide IDAS, NEXEDGE) |
| 8K30F1W | Phase I P25, C4FM Hybrid Voice and Data Applications |
| 8K30F7W | NXDN 12.5 kHz, digital voice and data (Wide IDAS, NEXEDGE) |
| 8K50F9W | Harris OpenSky (2 slots, narrowband) |
| 8K70D1W | P25, linear simulcast modulation ASTRO (9.6 kbit/s, channel 12.5 kHz) |
| 9K20F2D | Alphabetical digital paging/alert system based on Zetron |
| 9K30F1D | SCADA/Remote control |
| 9K70F1D | P25, linear simulcast "WCQPSK", data (Harris MASTR-V) |
| 9K70F1E | P25, linear simulcast "WCQPSK", voice (Harris MASTR-V) |
| 9K80D7W | P25 phase II, stage part, 2 slots TDMA H-DQPSK (Motorola) |
| 9K80F1D | P25 phase II, stage part, 2 TDMA H-DQPSK slots, data (Harris MASTR-V) |
| 9K80F1E | P25 phase II, stage part, 2 slots TDMA H-DQPSK, voice |
| 10K0F1D | LTI AVL - LT6 radio modem |
| 10K0F1D | RD-LAP, 9.6 kbps data, narrowband channel |
| 10K0F1D | Motorola Widepulse ASTRO data simulcast |
| 10K0F1D | Motorola Widepulse ASTRO, simulcast control channel |
| 10K0F1E | Motorola Widepulse ASTRO, voice simulcast |
| **11K0F3D** | **Narrowband FM 12.5 kHz APRS** |
| **11K0F3E** | **Narrowband FM 12.5 kHz Voice** |
| **11K0F3G** | **Narrowband FM 12.5 kHz Voice + APRS** |
| 11K2F2D | FM, 2.5 kHz deviation, AFSK in 12.5 kHz channel (packages 1.2 kbps, FFSK, sirens) |
| 11K2F3D | FM, 2.5 kHz deviation, DTMF and other tone signals (Whelen sirens, Knox-Box®) |
| 11K2F3E | FM, deviation of 2.5 kHz, analog voice, narrowband 12.5 kHz |
| 11K2F9W | Previously incorrectly used as a universal narrowband designation |
| 12K1F9W | Harris OpenSky (NPSPAC, 4 slots) |
| 13K1F9W | Harris OpenSky (SMR, 4 slots) |
| 13K6F3E | Analog voice with FM, deviation of 3.8 kHz (900 MHz) |
| 13K6W7W | Motorola iDEN (900 MHz) |
| 14K0F1D | Motorola, 3600 baht trunking control channel (NPSPAC) |
| 16K0F1D | Motorola, trunking control channel 3600 baud |
| 16K0F2D | World Cup, deviation 4 kHz, AFSK (fire detectors 72 MHz) |
| 16K0F3E\* | 4 kHz deviation, analog voice (NPSPAC) |
| **16K0F3D** | **Wideband FM 25 kHz APRS** |
| **16K0F3E** | **Wideband FM 25 kHz Voice** |
| **16K0F3G** | **Wideband FM 25 kHz Voice + APRS** |
| 16K8F1E\* | Encrypted Quantized Voice (Motorola DVP, DES, DES-XL, NPSPAC) |
| 17K7D7D7D | Motorola HPD – “Astro 25”, HAI, 700/800 MHz, 25 kHz channel |
| 20K0D1E | Tetra down. PowerTrunk 4/TDMA part (voice) |
| 20K0D1W | Tetra down. PowerTrunk 4/TDMA (mixed modes) |
| 20K0F1D | RD-LAP, 19.2 kbps, broadband channel |
| 20K0F1E | Encrypted Quantized Voice (Motorola DVP/DES/DES-XL – NOT P25) |
| 20K0F3E | FM, 5 kHz deviation, analog voice, 25 kHz broadband |
| 20K0G7W | Motorola iDEN (800 MHz) |
| 20K0W7W | Motorola iDEN (800 MHz) |
| 20K1D1D1D | Tetra down. PowerTrunk 4/TDMA part (data) |
| 21K0D1W | Standard TETRA ETS 300 392 |
| 30K0DXW | Cellular TDMA (North America) |
| 40K0F8W | cellular AMPS |
| 55K0P0N | Oceanographic radar CODAR (KV, scan ~1 s) - 3.5-5 MHz |
| 100KC3F | Video from ReconRobotics (430-450 MHz) |
| 100KP0N | Oceanographic radar CODAR (KV, scan ~1 s) - 12-14 MHz |
| 170KP0N | CODAR oceanographic radar above 24 MHz |
| 200KF8E | Broadcasting World Cup with additional subcarrier (SCA) |
| 250KF3E | Television broadcast sound (analog NTSC) |
| 300KG7W | EDGE |
| 300KGXW | GSM cellular |
| 1M25F9W | CDMA cellular |
| 2M40W7D | Remote control video (digital, not NTSC) |
| 5M00G7D | LTE security services, 5 MHz band |
| 5M00W7W | LTE security services, 5 MHz band |
| 5M00G2D | LTE security services, 5 MHz band |
| 5M00D7D | LTE security services, 5 MHz band |
| 5M75C3F | Television, NTSC analog video (with sound carrier) |
| 6M00C7W | Television, ATSC Digital TV |
| 10M0G2D | LTE security services, 10 MHz band |
| 10M0W7W | LTE security services, 10 MHz band |
| 10M0D7D | LTE security services, 10 MHz band |
| 10M0G7D | LTE security services, 10 MHz band |

\* - lines marked "\*" have footnotes on the source page that were not preserved when the text was extracted; symbols are transmitted as in the original.