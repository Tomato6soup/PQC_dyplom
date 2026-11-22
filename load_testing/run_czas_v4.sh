#!/bin/bash
set -u
cd "$(dirname "$0")" || exit 1
DURATIONS="${C_DURATIONS:-30 60 90 180}"
for D in $DURATIONS; do
echo "##### czas pomiaru ${D}s, start $(date '+%F %H:%M:%S') #####"
M_DURATION_S="$D" M_RUNTIMES="default" M_USERS="1 10 100" M_REPEATS=5 M_LOGDIR="logs_czas_${D}s" bash run_matrix_v3b.sh > "matrix_czas_${D}s.out" 2>&1
rc=$?
echo "##### czas ${D}s zakonczony kodem ${rc}, $(date '+%F %H:%M:%S') #####"
if [[ "$rc" -ne 0 ]]; then
echo "Przerwano na czasie ${D}s. Po usunieciu przyczyny uruchom ponownie: gotowe przebiegi zostana pominiete."
exit "$rc"
fi
done
echo "Wszystkie czasy gotowe: $DURATIONS"
