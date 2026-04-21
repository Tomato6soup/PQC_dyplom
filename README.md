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

## Autorka:
**_Anna Tkach_ _2026_**
