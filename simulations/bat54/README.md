# BAT54 clamp DC simulation

The nominal manufacturer model predicts **Vf = 0.2003 V at 0.7727 mA and 25°C**.
In the full 5 V / 2.2 kΩ / 3.3 V clamp circuit, the operating point is
**0.6834 mA and Vf = 0.1965 V**. The diode drop reduces the current relative to
the resistor-only bound `(5 − 3.3) / 2.2 kΩ = 0.7727 mA`.

This is the simulation evidence for the user's accepted BAT54 forward-voltage
margin. The current BOM uses five single diodes for easier routing; the simulated
one-junction circuit and its operating conditions are unchanged.

## Model and scope

- Engine: **ngspice 45.2**, using KiCad's bundled shared library.
- Model: **Diodes Incorporated / Zetex BAT54 v1.0, revised 2000-04-25**.
- Original download: [manufacturer BAT54 model](https://www.diodes.com/spice/download/510/BAT54.spice.txt), linked from the [BAT54 product page](https://www.diodes.com/part/view/BAT54).
- [BAT54.lib](BAT54.lib) retains the downloaded model and original notice intact.
- Selected BOM part: **R+O BAT54X, C19627026, SOD-523**. The simulation model is a different
  manufacturer's nominal BAT54 junction model, used as a proxy for the single
  diode. No qualified R+O BAT54X process-corner model was
  established during this work.

The analysis uses DC operating points and junction temperature sensitivity. It
does not model manufacturing spread, self-heating, the MCU's internal protection,
capacitive input edges, rail startup or the regulator's transient response.
The 3.3 V rail is an ideal voltage source for this isolated forward-drop study;
the separate [rail-load calculation](../../tools/check_clamp_budget.py) checks
whether the two 1 kΩ load resistors can absorb the five-input injection budget.

## Results

| Temperature | Vf at forced 0.7727 mA | Full nominal circuit current | Full nominal circuit Vf | Supply/resistor corner current | Supply/resistor corner Vf |
| --- | --- | --- | --- | --- | --- |
| −20°C | 0.2650 V | 0.6543 mA | 0.2606 V | 0.8035 mA | 0.2660 V |
| 0°C | 0.2364 V | 0.6672 mA | 0.2322 V | 0.8164 mA | 0.2379 V |
| 25°C | **0.2003 V** | **0.6834 mA** | **0.1965 V** | 0.8326 mA | 0.2026 V |
| 70°C | 0.1348 V | 0.7127 mA | 0.1320 V | 0.8620 mA | 0.1387 V |

The supply/resistor corner uses **5.25 V input, 3.234 V rail and 2178 Ω**. It
changes circuit values only; it is not a diode manufacturing corner. In all the
reported cases, this model's forward drop remains below 0.3 V. At 25°C, forced
0.5 mA gives 0.1871 V and forced 1 mA gives 0.2084 V. The screenshot's generic
typical-value table is not used to construct the model or its parameters.

Machine-readable evidence:

- [results.csv](results/results.csv): all forced-current and resistor-circuit operating points.
- [metadata.json](results/metadata.json): model source, SHA-256 and simulator version.
- [ngspice.log](results/ngspice.log): captured simulator output.
- [clamp.cir](clamp.cir): conventional nominal-case SPICE netlist.

## Reproduce

From the repository root:

```sh
python3 tools/simulate_bat54.py
```

The script uses Python's standard library and an installed ngspice shared library.
It discovers KiCad's bundled macOS library automatically; set `NGSPICE_LIBRARY`
to the library path on other installations if necessary. No package installation
or network access is required after the model is present.

With a standalone ngspice executable, run the equivalent single nominal case
from this directory:

```sh
ngspice -b clamp.cir
```

The optional `spinit` warning in the bundled-library log does not affect the
standard diode/resistor/DC-source circuit; no XSPICE code models are needed.
