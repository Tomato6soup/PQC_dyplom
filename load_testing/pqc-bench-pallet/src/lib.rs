#![cfg_attr(not(feature = "std"), no_std)]

pub use pallet::*;

#[frame_support::pallet]
pub mod pallet {
    use frame_support::pallet_prelude::*;
    use frame_system::pallet_prelude::*;
    use sp_core::ecdsa;
    extern crate alloc;
    use alloc::vec::Vec;

    use fips204::ml_dsa_44;
    use fips204::traits::{SerDes as MlDsaSerDes, Verifier as MlDsaVerifier};
    use fips205::slh_dsa_sha2_128f;
    use fips205::traits::{SerDes as SlhDsaSerDes, Verifier as SlhDsaVerifier};

    #[pallet::config]
    pub trait Config: frame_system::Config {
        type RuntimeEvent: From<Event<Self>> + IsType<<Self as frame_system::Config>::RuntimeEvent>;
    }

    #[pallet::pallet]
    pub struct Pallet<T>(_);

    #[pallet::storage]
    pub type VerifiedCount<T: Config> = StorageValue<_, u64, ValueQuery>;

    #[pallet::event]
    #[pallet::generate_deposit(pub(super) fn deposit_event)]
    pub enum Event<T: Config> {
        SignatureVerified { algo: u8, valid: bool, who: T::AccountId },
    }

    #[pallet::error]
    pub enum Error<T> {
        UnknownAlgorithm,
        MalformedPublicKey,
        MalformedSignature,
    }

    #[pallet::call]
    impl<T: Config> Pallet<T> {
        // algo: 0 = ECDSA (referencyjny klasyczny), 1 = Dilithium2 (ML-DSA-44), 2 = SPHINCS+ (SLH-DSA-128f)
        #[pallet::call_index(0)]
        #[pallet::weight(Weight::from_parts(50_000_000, 0))]
        pub fn submit_pqc_signature(
            origin: OriginFor<T>,
            algo: u8,
            message: Vec<u8>,
            signature: Vec<u8>,
            public_key: Vec<u8>,
        ) -> DispatchResult {
            let who = ensure_signed(origin)?;

            let valid = match algo {
                0 => {
                    let sig_bytes: [u8; 65] =
                        signature.as_slice().try_into().map_err(|_| Error::<T>::MalformedSignature)?;
                    let pk_bytes: [u8; 33] =
                        public_key.as_slice().try_into().map_err(|_| Error::<T>::MalformedPublicKey)?;
                    let sig = ecdsa::Signature::from_raw(sig_bytes);
                    let pk = ecdsa::Public::from_raw(pk_bytes);
                    sp_io::crypto::ecdsa_verify(&sig, &message, &pk)
                }
                1 => {
                    let pk_bytes: [u8; ml_dsa_44::PK_LEN] =
                        public_key.as_slice().try_into().map_err(|_| Error::<T>::MalformedPublicKey)?;
                    let sig_bytes: [u8; ml_dsa_44::SIG_LEN] =
                        signature.as_slice().try_into().map_err(|_| Error::<T>::MalformedSignature)?;
                    let vk = ml_dsa_44::PublicKey::try_from_bytes(pk_bytes)
                        .map_err(|_| Error::<T>::MalformedPublicKey)?;
                    vk.verify(&message, &sig_bytes, b"")
                }
                2 => {
                    let pk_bytes: [u8; slh_dsa_sha2_128f::PK_LEN] =
                        public_key.as_slice().try_into().map_err(|_| Error::<T>::MalformedPublicKey)?;
                    let sig_bytes: [u8; slh_dsa_sha2_128f::SIG_LEN] =
                        signature.as_slice().try_into().map_err(|_| Error::<T>::MalformedSignature)?;
                    let vk = slh_dsa_sha2_128f::PublicKey::try_from_bytes(&pk_bytes)
                        .map_err(|_| Error::<T>::MalformedPublicKey)?;
                    vk.verify(&message, &sig_bytes, b"")
                }
                _ => return Err(Error::<T>::UnknownAlgorithm.into()),
            };

            VerifiedCount::<T>::mutate(|c| *c += 1);
            Self::deposit_event(Event::SignatureVerified { algo, valid, who });

            Ok(())
        }
    }
}
