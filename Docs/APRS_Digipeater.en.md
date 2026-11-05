# APRS Digipeater Explained - Paths and WIDE1-1/WIDE2-1 · APRS World

Original: https://aprs.world/guides/aprs-digipeater-explained

# APRS Digipeater Explained - Paths, WIDE1-1, WIDE2-1 and the New N Paradigm

If you have ever opened a live map on aprs. And they wondered how a low-powered walkie-talkie in a remote valley ends up on a website in seconds, and the answer is almost always:**digipeater**(Digital Relayer), which listens to packets at the local APRS frequency, decides whether they can be repeated, and relays them at the same frequency to long-distance stations.[iGates](/guides/aprs-igate-setup)You could hear them. Digipeaters are APRS binders on the air, and their configuration directly depends on whether the network will be efficient or congested.

This guide explains what a digipeater is, what mysterious lines of the species actually mean`WIDE1-1,WIDE2-1`Why the network has moved away from the old ways`RELAY,WIDE,TRACE`In the early 2000s, what's the difference between a fill-in digi at the foot of a hill and a wide-area digi at the top of a mountain? You're supposed to know something.[What is APRS?](/guides/what-is-aprs).

## What does Digipeater do?

Digipeater is essentially an ordinary APRS station configured to relay packets on behalf of others. He hears the package on the air, he studies a special field.**The Digipeater Path (Digipeater Path)**which the original station included in its title[AX.25](https://en.wikipedia.org/wiki/AX.25), and if there are unused hops (jumps) on the way, the repeater queues the packet, waits for an access interval to the channel and transmits it again at the same frequency. Any other station — radio, iGate, or another digi — that is within range of the repeater can now hear the packet, even if the source transmitter was out of range.

The mechanism dates back to the standard packet radio AX.25 of the 1980s; APRS only imposes on it an agreement accepted by the community. No special hardware is required: most digipeaters are regular computers (or Raspberry Pi) with software like this.[Direwolf](https://github.com/wb2osz/direwolf), [prx](https://github.com/PhirePhly/aprx), [YAAC](https://www.ka2ddo.org/ka2ddo/YAAC.html)or[Xastir](https://github.com/Xastir/Xastir)connected to the transceiver and sound card. Some commercial radios with built-in TNC — Kenwood TM-D710G, Yaesu FTM-400/500 — can also work as standalone digipeaters without a PC at all.

## Anatomy of the APRS pathway

Each APRS packet carries**path**In the AX.25 field, a comma-separated list of call signs or alias tokens describing how the sender wants to distribute the packet. A typical mobile beacon on the air looks something like this:

```
TA4OHN-9>APRS,WIDE1-1,WIDE2-1:!4030.00N/03253.00E>Mobile
```

Part after`APRS`And to the colon.`WIDE1-1,WIDE2-1`- it's a path request. It reads from left to right. Numerical suffix`-N`Each alias has a counter that decreases every time the digipeater absorbs the hop. When the counter reaches zero, the alias is marked as “used” (in the etheric format the bit is switched, and in the readable dumps an asterisk is added at the beginning) – and no other digipeater touches it.

In simple words:`WIDE1-1,WIDE2-1`It means, “I am ready to repeat myself.”**single**WIDE1 class digi (usually low, local fill-in)**и**before**two**WIDE2 class digi (usually large-format mining rigs)”. This is enough for most mobile lighthouses to cross the urban agglomeration without clogging the canal.

## The New N-Paradigm

If you've read the old APRS documentation of the 1990s and early 2000s, you'll see links on paths like`RELAY,WIDE,TRACE2-2`or`RELAY,WIDE7-7`. It's**paradigm**It is not recommended anywhere else in the world. It caused a huge congestion of the channel because there was no normal way to limit hops at the network level - a misconfigured tracker could (and did) flood entire countries with repeat copies of a single beacon.

Solution.**The New N-Paradigm**It was compiled by Bob Bruninga and several network operators around 2004 and is now virtually standard everywhere. The full text is on[aprs.org/newN/new-paradigm.txt](http://www.aprs.org/newN/new-paradigm.txt). Three key ideas:

1. **Two levels of alias.** `WIDE1-1`designed**fill-in**digipeaters are low-power installations at low altitudes, whose task is to pick up packets from wearable walkie-talkies in the valleys and re-radiate them once to be heard by the nearest wide-area digi.`WIDE2-N`designed**wide-area**digipeaters are well-located mountain or tower installations covering hundreds of square kilometers.
2. **Tough limits on hops.**Most networks limit the number of mobile paths`WIDE1-1,WIDE2-1`(actually two hops), and home stations up to`WIDE2-2`(two hops) Fixed iGates often transmit a lighthouse with no path at all.`WIDE2-1`Or empty), because they don't need a relay - they're already online.
3. **Hop counter discipline.**Each digi reduces the counter by exactly one. Old tracker firmware that had reduced it incorrectly has been decommissioned.

The shorter the path, the better the network behaves. The old-timers will still say, “Use the minimum path by which you will be heard”; it follows that the paths are longer.`WIDE1-1,WIDE2-2`A sign of poor settings, except for truly remote terrain.

## Fill-In Digis vs Wide-Area Digis

The conceptual separation of fill-in and wide-area digi is the cleanest way to think about the modern web.

**Fill-in- digis**(sometimes referred to as WIDE1-only digis) stand low - in a city block, in a coastal town, in a campus building. Their radio horizon is small, about 10-20 km, but they are deliberately placed where there is a population density and where mobile stations would otherwise be invisible. Fill-in digi repeats only those packets whose path requests`WIDE1-1`. He doesn't touch the packages.`WIDE2-N`- they're for bigger stations. A classic example: a wearable radio in the city "canyon" from skyscrapers transmits a lighthouse with a path`WIDE1-1,WIDE2-1`. Local fill-in catches it and re-radiates with the spent slot`WIDE1`; then the wide-area digi at 80 km on the mountain catches re-radiation and spreads it further.

**Wide-area digis**Stand high: tower 600 meters, mountain house, roof of a high-rise building. They listen to traffic.`WIDE2-N`And re-emit it once, reducing the meter. Since their radio horizon is huge – often 150 km or more – they only need to fire once per packet to cover an entire region. A well-placed wide-area digi handles thousands of packets a day. Access to the channel needs to be carefully managed: two wide-area digi, whose coverage areas overlap, both will hear the original packet, and both will want to repeat it - which is why APRS digipeaters widely use a randomized waiting timer (the famous "dwait" and "p-persist" parameters) before turning on a transmission.

A sensible regional network has one wide-area digi per major relief element and a fill-in digi scatter around population centers. Build it in reverse (many wide-area, no fill-in) and you overload the channel without hearing the city's wearable walkie-talkie.

## Special aliases

The new N-paradigm also defines several non-conventional WIDE hop aliases:

* **`SAR`**Search and Rescue (Search and Rescue) Used in incident management to flag traffic that needs to be prioritized. Not all networks support it; check with your local emergency coordinator.
* **`TEMP1-1`, `TEMP2-1`**Temporary deployment aliases for portable digi at events. Configured exactly like WIDE, but held separately so as not to conflict with the permanent infrastructure.
* **`ECHO`**One-hop alias to check the connection. Pass the beacon with the path`ECHO`- and only your local digi should repeat you back; useful to confirm that you reach the local station.
* **Country/regional aliases**Some national networks use aliases with a country letter (e.g.`GATE`, `NOGATE`) for traffic that should or should not pass through certain points of the gateway.

Most operators will never have to go outside.`WIDE1-1,WIDE2-1`mobile`WIDE2-2`For fixed home stations.

## How to Know Where Your Package Has Been

Open any decoded package in a tool like[aprs.fi.](https://aprs.fi/), [aprs.world](https://aprs.world/)Or the console listener and look at the field. Each digipeater through which the packet has passed adds its own call sign with the final asterisk to indicate that the packet has passed through it. A package originally sent as:

```
TA4OHN-9>APRS,WIDE1-1,WIDE2-1
```

You can get to iGate in this form:

```
TA4OHN-9>APRS,TA1FILL-1*,TA1WIDE-3*,WIDE2*
```

This track means that it was repeated first.`TA1FILL-1`(Local fill-in digi, spent slot)`WIDE1-1`then`TA1WIDE-3`(wide-area station that consumed the first hop)`WIDE2-1`), and then it was picked up by iGate. Reading the track in reverse order is the quickest way to know which digi is hearing you and which is not.

## Launching your own Digipeater

If you want to add capacity to your local network, the recipe is simple:

1. **Pick a dot.**Fill-in: a place with direct visibility to the center of the population, which is now "not covered". Wide-area: High point with direct visibility to other wide-area stations.
2. **Choose iron.**Raspberry Pi 4, sound interface[DigiRigig.](https://digirig.net/), [Mobilinkd TNC](https://www.mobilinkd.com/)or homemade opto-insulated cable) and a transceiver configured to the local APRS frequency[frequency tables](/guides/aprs-frequencies-by-country).
3. **Set it up.**Direwolf is the modern default standard; it includes both the software TNC and the digipeater module. The configuration file determines if you are working as a fill-in.`DIGIPEAT 0 0 ^WIDE1-1$ ^`) or as wide-area (`DIGIPEAT 0 0 ^WIDE[12]-[1-7]$ ^`).
4. **Contact the APRS Regional Coordinator.**Most countries have a volunteer who monitors call signs and digi coverage areas so there are no intersections. Telling him you're on the air is a good tone and allows you not to step on someone else's cover.

Work 24/7 with backup power and you’ll be part of APRS’ public infrastructure in your area. Few hobbies give it for the price of a Pi and a clean antenna track.

## Where Digipeater Transfers the Relay to the Internet

The work of digipeater ends on air; delivery of packages to the global network is a task**iGate**. Many stations combine both roles on the same Pi - Direwolf and aprx are happy to do both at the same time. However, the separation of roles is important: pure digi without iGate still adds value to the local radio network, and pure iGate without digi still adds value to the global Internet broadcast. Details in the accompanying[Guide to setting up iGate](/guides/aprs-igate-setup)How the internet works, and how it works,[explanation of the APRS-IS network](/guides/aprs-is-network-explained).

## Where to Read Next

* Canonical[N-paradigm](http://www.aprs.org/newN/new-paradigm.txt)Aprs.org is short and worth reading.
* [Direwolf user manual](https://github.com/wb2osz/direwolf)The software side of the launch of modern digi.
* [Project aprx](https://github.com/PhirePhly/aprx)Easy alternative to C, loved for low consumption of resources on Pi.
* Ours.[Guide "What is APRS"](/guides/what-is-aprs)for the context of the protocol, and[FAQ by APRS](/guides/aprs-faq)- for short answers.

The network of digipeaters is what makes APRS magical on the part of the operator: you press a button and you're on a map all over the country. Understanding how it works is the difference between using APRS and trusting it.