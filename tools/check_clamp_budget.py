#!/usr/bin/env python3
"""Reproduce the prototype's DC rail-current budget, not a GPIO safety proof."""
import math

v_target_max = 5.25
v_rail_min = 3.3 * 0.98
v_rail_max = 3.3 * 1.02
r_series_min = 2200 * 0.99
r_bleed_max = 1000 * 1.01

# Zero forward voltage maximizes injection: no dependence on weak TTL HIGH drive.
injection_max = 5 * (v_target_max - v_rail_min) / r_series_min
sink_min = 2 * v_rail_min / r_bleed_max
assert sink_min > injection_max
assert v_rail_max**2 / (1000 * 0.99) < 0.0625
print(f'Injection upper bound: {injection_max*1000:.3f} mA')
print(f'Bleed load minimum:    {sink_min*1000:.3f} mA')
print(f'Current margin:        {(sink_min-injection_max)*1000:.3f} mA')
print(f'Illustrative 20 pF node: tau={2200*20e-12*1e9:.1f} ns; '
      f'2.4 V step to 2.0 V={-2200*20e-12*math.log(1-2.0/2.4)*1e9:.1f} ns')
print('Accepted design risk: use the BAT54 clamps at sub-mA current; '
      'nominal SPICE evidence is in simulations/bat54. '
      'The model is not a guaranteed JSCJ process corner.')
