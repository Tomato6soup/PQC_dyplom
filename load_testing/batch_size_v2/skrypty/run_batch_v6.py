import os, subprocess, sys, time

os.chdir(os.path.dirname(os.path.abspath(__file__)))
uzytkownicy = os.getenv("C_USERS", "1 10 100").split()
rozmiary = os.getenv("C_BATCHES", "1 2 5 10 20 50").split()
prefix = os.getenv("C_LOGPREFIX", "logs_batchc")

for u in uzytkownicy:
    for b in rozmiary:
        env = dict(os.environ)
        env.update({
            "M_ALGOS": os.getenv("C_ALGOS", "ecdsa dilithium2 sphincs"),
            "M_USERS": u,
            "M_RUNTIMES": "default",
            "M_DURATION_S": os.getenv("C_DURATION", "120"),
            "M_REPEATS": os.getenv("C_REPEATS", "1"),
            "M_LOGDIR": prefix + "_U" + u + "_B" + b,
            "BATCH_SIZE": b,
            "BATCH_MODE": "burst",
            "BATCH_GAP_S": os.getenv("C_GAP", "0.05"),
        })
        wyjscie = "matrix_" + prefix + "_U" + u + "_B" + b + ".out"
        print("##### U=" + u + " batch " + b + ", start " + time.strftime("%F %H:%M:%S") + " #####", flush=True)
        with open(wyjscie, "w") as f:
            rc = subprocess.run(["bash", "run_matrix_v6.sh"], env=env, stdout=f, stderr=subprocess.STDOUT).returncode
        print("##### U=" + u + " batch " + b + " zakonczony kodem " + str(rc) + ", " + time.strftime("%F %H:%M:%S") + " #####", flush=True)
        if rc != 0:
            print("Przerwano na U=" + u + " batch " + b + ". Po usunieciu przyczyny uruchom ponownie: gotowe przebiegi zostana pominiete.")
            sys.exit(rc)
print("Wszystko gotowe.")
