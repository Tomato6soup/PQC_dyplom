# Seria batch_size: B transakcji wysylanych bez przerw (tryb burst), pauza B x 0.05 s miedzy paczkami.
# Srednie obciazenie na uzytkownika jest takie samo dla kazdego B, zmienia sie tylko "zbitka" transakcji.
import os, subprocess, sys, time

os.chdir(os.path.dirname(os.path.abspath(__file__)))
rozmiary = os.getenv("C_BATCHES", "1 2 5 10 20 50").split()
prefix = os.getenv("C_LOGPREFIX", "logs_batch")

for b in rozmiary:
    env = dict(os.environ)
    env.update({
        "M_ALGOS": os.getenv("C_ALGOS", "ecdsa dilithium2 sphincs"),
        "M_USERS": os.getenv("C_USERS", "1"),
        "M_RUNTIMES": "default",
        "M_DURATION_S": os.getenv("C_DURATION", "120"),
        "M_REPEATS": os.getenv("C_REPEATS", "5"),
        "M_LOGDIR": prefix + "_B" + b,
        "BATCH_SIZE": b,
        "BATCH_MODE": "burst",
    })
    wyjscie = "matrix_" + prefix + "_B" + b + ".out"
    print("##### batch " + b + ", start " + time.strftime("%F %H:%M:%S") + " #####", flush=True)
    with open(wyjscie, "w") as f:
        rc = subprocess.run(["bash", "run_matrix_v5.sh"], env=env, stdout=f, stderr=subprocess.STDOUT).returncode
    print("##### batch " + b + " zakonczony kodem " + str(rc) + ", " + time.strftime("%F %H:%M:%S") + " #####", flush=True)
    if rc != 0:
        print("Przerwano na batch " + b + ". Po usunieciu przyczyny uruchom ponownie: gotowe przebiegi zostana pominiete.")
        sys.exit(rc)
print("Wszystkie rozmiary gotowe: " + " ".join(rozmiary))
