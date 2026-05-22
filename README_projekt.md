# Post-Quantum Cryptography (PQC) Impact on Blockchain Scalability

Niniejszy projekt został zrealizowany w ramach pracy inżynierskiej i skupia się na analizie wpływu algorytmów kryptografii postkwantowej na wydajność i skalowalność sieci blockchain. Głównym celem jest zbadanie, jak zwiększony rozmiar podpisów PQC (np. Dilithium, Sphincs+) wpływa na czas propagacji bloków oraz przepustowość sieci.

## 🚀 Główne Cele Projektu

   **Implementacja parametrów PQC:** Dostosowanie węzła blockchain (Substrate) do obsługi zwiększonych limitów danych.

   **Symulacja sieci:** Przeprowadzenie testów propagacji dla różnych liczebności węzłów (10, 50, 100) przy użyciu symulatora SimBlock.

   **Analiza Skalowalności:** Porównanie wydajności klasycznych podpisów (ECDSA/Ed25519) z rozwiązaniami postkwantowymi.

   **Wizualizacja Danych:** Automatyczna generacja wykresów zależności czasu propagacji od rozmiaru bloku i liczby peerów.

## 🛠️ Stos Technologiczny

   **Blockchain:** Substrate SDK/Polkadot SDK (Rust) – modyfikacja parametrów Runtime (BlockLength, BlockWeights).

   **Symulacja:** SimBlock (Java/Gradle) – modelowanie opóźnień sieciowych w skali globalnej.

   **Analiza Danych:** Python 3 (Pandas, Matplotlib) – przetwarzanie logów i generowanie wykresów statystycznych.

   **Środowisko:** Ubuntu Linux / Oracle VirtualBox.

## 📊 Metodyka Badań

Eksperymenty zostały podzielone na dwa główne nurty:

   **Testy na realnym węźle (Substrate)**: Pomiar czasu weryfikacji bloków o rozmiarach 5MB, 10MB oraz 20MB.

   **Symulacje sieciowe (SimBlock)**: Badanie czasu rozchodzenia się informacji w topologii P2P przy założeniu narzutu danych generowanego przez podpisy PQC.

   Przygotowanie danych o rozmiarach:
   
Na podstawie literatury (np. dokumentacji NIST) przyjęto parametry dla 128-bitowego poziomu bezpieczeństwa:

    Ed25519 (Klasyczny): Podpis: 64 B, Klucz publiczny: 32 B.

    Dilithium2 (PQC): Podpis: 2420 B, Klucz publiczny: 1312 B.

    SPHINCS+-128f (PQC): Podpis: 17088 B, Klucz publiczny: 32 B.

Wyliczenie narzutu na blok (Overhead):
Załóżmy, że blok zawiera 500 transakcji. Obliczamy całkowity rozmiar danych podpisów w bloku:

    Klasyczny: 500×96 B≈0.048 MB.

    Dilithium: 500×3.7 KB≈1.8 MB.

    SPHINCS+: 500×17 KB≈8.5 MB.

## Autorka:
**_Anna Tkach_ _2026_**
