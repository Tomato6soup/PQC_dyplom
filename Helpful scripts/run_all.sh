#!/bin/bash
# katalog na wyniki
mkdir -p wyniki

# seedy
SEEDS="10 20 30 40 50 60 70 80 90 100"
# rozmiary sieci
NODES="500 1000 1500 2000 4000"

# scenariusze: nazwa  blocksize  verifms
# (kolejno: algorytm_tx  BLOCK_SIZE  blockVerificationTimeMs)
SCENARIOS=(
  "ecdsa_500 125000 59"
  "ecdsa_1000 250000 141"
  "ecdsa_1500 375000 217"
  "ecdsa_2000 500000 255"
  "dilithium_500 1941000 111"
  "dilithium_1000 3882000 114"
  "dilithium_1500 5823000 253"
  "dilithium_2000 7764000 233"
  "sphincs_500 4019000 1514"
  "sphincs_1000 8038000 3267"
  "sphincs_1500 12057000 3881"
  "sphincs_2000 16076000 5105"
)

for scen in "${SCENARIOS[@]}"; do
  set -- $scen
  NAME=$1; BSIZE=$2; VMS=$3
  for n in $NODES; do
    for s in $SEEDS; do
      echo ">>> $NAME  N=$n  seed=$s"
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
