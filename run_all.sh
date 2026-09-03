#!/bin/bash
# run_all.sh — komplet 600 symulacji SimBlock
# WERSJA ZAKTUALIZOWANA: verifms = mediany z powtórzonych mikrotestów Rust
# (blocksize bez zmian — zależy od rozmiaru podpisu, nie od czasu weryfikacji)

# katalog na wyniki
mkdir -p wyniki

# seedy
SEEDS="10 20 30 40 50 60 70 80 90 100"
# rozmiary sieci
NODES="500 1000 1500 2000 4000"

# scenariusze:  nazwa  blocksize  verifms(mediana z mikrotestów)
SCENARIOS=(
  "ecdsa_500 125000 33"
  "ecdsa_1000 250000 65"
  "ecdsa_1500 375000 110"
  "ecdsa_2000 500000 161"
  "dilithium_500 1941000 40"
  "dilithium_1000 3882000 75"
  "dilithium_1500 5823000 129"
  "dilithium_2000 7764000 135"
  "sphincs_500 4019000 1141"
  "sphincs_1000 8038000 2282"
  "sphincs_1500 12057000 3410"
  "sphincs_2000 16076000 4938"
)

for scen in "${SCENARIOS[@]}"; do
  set -- $scen
  NAME=$1; BSIZE=$2; VMS=$3
  for n in $NODES; do
    for s in $SEEDS; do
      echo ">>> $NAME  N=$n  seed=$s  (blocksize=$BSIZE verifms=$VMS)"
      ./gradlew run -q \
        -Dseed=$s \
        -Dnodes=$n \
        -Dblocksize=$BSIZE \
        -Dverifms=$VMS \
        > wyniki/${NAME}_N${n}_seed${s}.txt
    done
  done
done
echo "Gotowe. Wyniki w katalogu wyniki/"
