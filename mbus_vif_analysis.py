"""
M-Bus VIF (Value Information Field) Analyse
Nach EN 13757-3 Standard

VIF Codes für verschiedene Einheiten:
- Energy Wh: 0x00-0x07 (E000 0nnn) -> 10^(nnn-3) Wh
- Power W:  0x28-0x2F (E010 1nnn) -> 10^(nnn-3) W  
- Voltage:  0x48-0x4F (E100 1nnn) -> 10^(nnn-3) V
- Current:  0x50-0x57 (E101 0nnn) -> 10^(nnn-3) A

Beispiele für typische VIF-Werte:
- 0x03: Energy in 10^(3-3) = 10^0 = 1 Wh
- 0x04: Energy in 10^(4-3) = 10^1 = 10 Wh
- 0x07: Energy in 10^(7-3) = 10^4 = 10000 Wh = 10 kWh

Problem mit den großen Zahlen:
Ein Wert von 1.828.978.688 mit VIF 0x04 bedeutet:
1.828.978.688 * 10 Wh = 18.289.786.880 Wh = 18.289.787 kWh

Das ist offensichtlich falsch!

Das Problem liegt wahrscheinlich daran, dass:
1. Die Rohdaten bereits skaliert sind (z.B. in 0.1 Wh Einheiten)
2. Der VIF-Code eine andere Bedeutung hat
3. Die Byte-Reihenfolge falsch interpretiert wird

Lass uns schauen was passiert wenn der Rohwert bereits in 0.1 Wh ist:
1.828.978.688 * 0.1 Wh = 182.897.868.8 Wh = 182.898 kWh
Immer noch zu groß!

Oder in 0.01 Wh:
1.828.978.688 * 0.01 Wh = 18.289.786.88 Wh = 18.290 kWh
Das könnte realistisch sein!

Spannung 2301 mit falschem VIF:
Wenn der Rohwert 2301 Hundertstel Volt sind (0.01 V):
2301 * 0.01 = 23.01 V
Das ist viel zu niedrig für Netzspannung!

Wenn 2301 Hundertstel von 100V sind:
2301 * 0.01 + 200 = 223.01 V
Das könnte stimmen!

Oder wenn es direkt Zehntel Volt sind:
2301 / 10 = 230.1 V
Das ist perfekt für EU-Netzspannung!
"""

print("Analyse der M-Bus VIF-Codes...")
print("Siehe Kommentare in der Datei für Details.")

# Test verschiedene Interpretationen
raw_value = 1828978688
print(f"\nRohwert: {raw_value}")
print(f"Als 0.01 Wh: {raw_value * 0.01} Wh = {raw_value * 0.01 / 1000} kWh")
print(f"Als 0.001 Wh: {raw_value * 0.001} Wh = {raw_value * 0.001 / 1000} kWh")

voltage_raw = 2301
print(f"\nSpannungs-Rohwert: {voltage_raw}")
print(f"Als 0.1 V: {voltage_raw * 0.1} V")
print(f"Als 0.01 V: {voltage_raw * 0.01} V")
print(f"Als ganze V: {voltage_raw} V")