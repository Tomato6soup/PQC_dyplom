use pqcrypto_dilithium::dilithium2::*;
use std::time::Instant;
use std::fs::File;
use std::io::Write;

fn main() {
    println!("--- BENCHMARK WERYFIKACJI BLOKOW (DILITHIUM2) ---");

    // Generowanie kluczy
    let (pk, sk) = keypair();

    // Przykladowy payload transakcji (32-bajtowy hash)
    let msg = [0u8; 32];

    // Generowanie "podpisu oderwanego"
    let sig = detached_sign(&msg, &sk);

    // Rozmiary blokow (liczba transakcji)
    let block_sizes = [10, 50, 100, 200, 500, 1000, 1500, 2000];

    // Liczba POWTORZEN kazdego pomiaru
    let repeats = 50;

    // Rozgrzewka
    for _ in 0..5 {
        let _ = verify_detached_signature(&sig, &msg, &pk).is_ok();
    }

    // Plik wyjsciowy CSV
    let mut plik = File::create("wyniki_dilithium.csv")
        .expect("Nie udalo sie utworzyc pliku CSV");
    writeln!(plik, "algorytm,tx_count,powtorzenie,czas_ms")
        .expect("Blad zapisu naglowka");

    for &tx_count in &block_sizes {
        for r in 0..repeats {
            let start = Instant::now();

            for _ in 0..tx_count {
                let _ = verify_detached_signature(&sig, &msg, &pk).is_ok();
            }

            let duration = start.elapsed();
            let czas_ms = duration.as_secs_f64() * 1000.0;

            writeln!(plik, "dilithium,{},{},{:.4}", tx_count, r, czas_ms)
                .expect("Blad zapisu wiersza");
        }
        println!("Blok {} tx -> wykonano {} powtorzen", tx_count, repeats);
    }

    println!("GOTOWE. Wyniki zapisano w pliku: wyniki_dilithium.csv");
}
