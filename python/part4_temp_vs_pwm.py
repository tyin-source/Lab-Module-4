# Phys 39 Module 4 - Part 4
# Steady-state temperature vs signed PWM (positive = HEAT, negative = COOL),
# with a separate straight-line fit for each direction.

import numpy as np
import matplotlib.pyplot as plt

# Data (data/module_04/part4_steady_state.csv)
heat_pwm = np.array([0, 12, 24, 35, 47])
heat_temp = np.array([23.48, 28.90, 35.35, 40.40, 46.10])

cool_pwm = np.array([-80, -60, -40, -20, 0])
cool_temp = np.array([9.83, 13.25, 16.82, 20.30, 23.48])

# Fits
m_h, b_h = np.polyfit(heat_pwm, heat_temp, 1)
m_c, b_c = np.polyfit(cool_pwm, cool_temp, 1)

print(f"m_h = {m_h:.3f} °C/count")
print(f"m_c = {m_c:.3f} °C/count")
print(f"r = {m_h/m_c:.2f}")

# Plot
plt.figure(figsize=(8, 5))
plt.scatter(heat_pwm, heat_temp, color='red', label='Heating')
plt.scatter(cool_pwm, cool_temp, color='blue', label='Cooling')

x_heat = np.linspace(0, 47, 100)
x_cool = np.linspace(-80, 0, 100)
plt.plot(x_heat, m_h*x_heat + b_h, 'r--', label=f'Heat fit: m={m_h:.3f}')
plt.plot(x_cool, m_c*x_cool + b_c, 'b--', label=f'Cool fit: m={m_c:.3f}')

plt.xlabel('Signed PWM (count)')
plt.ylabel('Steady Temperature (°C)')
plt.title('Temperature vs Signed PWM')
plt.legend()
plt.grid(True)
plt.axhline(0, color='black', linewidth=0.5)
plt.axvline(0, color='black', linewidth=0.5)
plt.savefig('docs/figures/module_04/part4_temp_vs_signed_pwm.png', dpi=100)
plt.show()
