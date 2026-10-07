# Phys 39 Module 5 - Part 2/3 gain plan (before running, for instructor approval)
#
# Uses the Module 4 susceptibility for the direction the controller must drive:
#   P_required = |Tset - Tamb| / |chi_T|          open-loop PWM for the change
#   P0         = Kp |e0|,  e0 = Tset - Tamb        initial PWM before clamping
#   L          = Kp |chi_T|                        dimensionless loop gain
#   droop      = e0 / (1 + L)                      predicted steady-state error
#   Tss        = Tset - droop
#   final PWM  = Kp |droop|
#
# Usage (from the repository root):
#   python python/module5_gain_plan.py --t-set 30 --t-amb 23.0
#   python python/module5_gain_plan.py --t-set 18 --t-amb 23.0 --kp 0.5 1 2
#
# Prints a Markdown table to paste into docs/module_notes/module_05_p_control.md.

import argparse

from module5_common import directional_susceptibility, module4_susceptibility

DEFAULT_KP = [0.5, 1, 2, 4, 8, 16, 32]   # doubling sequence, PWM counts per C


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t-set", type=float, required=True, help="setpoint (C)")
    ap.add_argument("--t-amb", type=float, required=True, help="room temperature (C)")
    ap.add_argument("--kp", type=float, nargs="+", default=DEFAULT_KP,
                    help="candidate gains (PWM counts per C)")
    args = ap.parse_args()

    chi_h, abs_chi_c = module4_susceptibility()
    direction, chi = directional_susceptibility(args.t_set, args.t_amb)
    e0 = args.t_set - args.t_amb
    p_required = abs(e0) / chi

    print(f"Module 4 susceptibility: chi_h = {chi_h:.3f} C/count, "
          f"|chi_c| = {abs_chi_c:.3f} C/count")
    print(f"Tset = {args.t_set:.2f} C, Tamb = {args.t_amb:.2f} C, "
          f"e0 = {e0:+.2f} C -> {direction}, using |chi_T| = {chi:.3f} C/count")
    print(f"P_required = |e0| / |chi_T| = {p_required:.1f} PWM counts")
    print(f"Largest Kp with P0 <= 255: {255 / abs(e0):.1f} PWM/C")
    print()
    print("| Kp (PWM/C) | L = Kp|chi_T| | Predicted P0 | P0 / P_required "
          "| Predicted droop (C) | Predicted Tss (C) | Predicted final PWM |")
    print("| ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for kp in args.kp:
        L = kp * chi
        p0 = kp * abs(e0)
        droop = e0 / (1 + L)
        flag = "  (P0 > 255: starts saturated)" if p0 > 255 else ""
        print(f"| {kp:g} | {L:.2f} | {p0:.1f}{flag} | {p0 / p_required:.2f} "
              f"| {droop:+.2f} | {args.t_set - droop:.2f} | {kp * abs(droop):.1f} |")


if __name__ == "__main__":
    main()
