use secp256k1::{Secp256k1, Message};
use rand::rngs::OsRng;
use std::time::Instant;
use std::fs::File;
use std::io::Write;

fn main() {
    println!("--- BENCHMARK WERYFIKACJI BLOKOW (ECDSA - secp256k1) ---");

    // Inicjalizacja biblioteki i generowanie pary kluczy
    let secp = Secp256k1::new();
    let (secret_key, public_key) = secp.generate_keypair(&mut OsRng);

    // Przykladowy payload transakcji (32-bajtowy hash)
    let msg_bytes = [0u8; 32];
    let message = Message::from_slice(&msg_bytes).expect("Blad dlugosci wiadomosci");

    // Generowanie referencyjnego podpisu
    let signature = secp.sign_ecdsa(&message, &secret_key);

    // Rozmiary blokow (liczba transakcji)
    let block_sizes = [10, 50, 100, 200, 500, 1000, 1500, 2000];

    // Liczba POWTORZEN kazdego pomiaru
    let repeats = 50;

    // Rozgrzewka
    for _ in 0..5 {
        let _ = secp.verify_ecdsa(&message, &signature, &public_key).is_ok();
    }

    // Plik wyjsciowy CSV
    let mut plik = File::create("wyniki_ecdsa.csv")
        .expect("Nie udalo sie utworzyc pliku CSV");
    writeln!(plik, "algorytm,tx_count,powtorzenie,czas_ms")
        .expect("Blad zapisu naglowka");

    for &tx_count in &block_sizes {
        for r in 0..repeats {
            let start = Instant::now();

            for _ in 0..tx_count {
                let _ = secp.verify_ecdsa(&message, &signature, &public_key).is_ok();
            }

            let duration = start.elapsed();
            let czas_ms = duration.as_secs_f64() * 1000.0;

            writeln!(plik, "ecdsa,{},{},{:.4}", tx_count, r, czas_ms)
                .expect("Blad zapisu wiersza");
        }
        println!("Blok {} tx -> wykonano {} powtorzen", tx_count, repeats);
    }

    println!("GOTOWE. Wyniki zapisano w pliku: wyniki_ecdsa.csv");
}
