def zamien(tekst, stare, nowe):
    if tekst.count(stare) != 1:
        raise SystemExit("BLAD: fragment znaleziono " + str(tekst.count(stare)) + " razy: " + stare)
    return tekst.replace(stare, nowe)

m = open("run_matrix_v5.sh").read()
m = zamien(m, "-f locustfile_v5_batch.py", "-f locustfile_v6_batch.py")
open("run_matrix_v6.sh", "w").write(m)

l = open("locustfile_v5_batch.py").read()
l = zamien(l, 'BATCH_MODE = os.getenv("BATCH_MODE", "seq")\n',
           'BATCH_MODE = os.getenv("BATCH_MODE", "seq")\nBATCH_GAP_S = float(os.getenv("BATCH_GAP_S", "0.05"))\n')
l = zamien(l, "            time.sleep(BATCH_SIZE / (1.0 / PACING_S))\n",
           "            time.sleep(BATCH_GAP_S)\n")
open("locustfile_v6_batch.py", "w").write(l)
print("OK: run_matrix_v6.sh i locustfile_v6_batch.py gotowe")
