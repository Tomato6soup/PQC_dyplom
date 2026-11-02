use fips204::ml_dsa_44;
use fips204::traits::{SerDes as _, Signer as _};
use fips205::slh_dsa_sha2_128f;
use fips205::traits::{SerDes as _, Signer as _};
use sp_core::{ecdsa, Pair};
use std::fs;

fn main() {
    let message = b"pqc-benchmark-test-message".to_vec();

    let ecdsa_pair = ecdsa::Pair::generate().0;
    let ecdsa_sig = ecdsa_pair.sign(&message);
    let ecdsa_pub = ecdsa_pair.public();

    let (ml_pub, ml_priv) = ml_dsa_44::try_keygen().expect("keygen ml-dsa-44");
    let ml_sig = ml_priv.try_sign(&message, &[]).expect("sign ml-dsa-44");

    let (slh_pub, slh_priv) = slh_dsa_sha2_128f::try_keygen().expect("keygen slh-dsa");
    let slh_sig = slh_priv.try_sign(&message, &[], false).expect("sign slh-dsa");

    let vectors = serde_json::json!({
        "message": hex::encode(&message),
        "ecdsa": {
            "public_key": hex::encode(ecdsa_pub.0),
            "signature": hex::encode(ecdsa_sig.0),
        },
        "dilithium2": {
            "public_key": hex::encode(ml_pub.into_bytes()),
            "signature": hex::encode(ml_sig),
        },
        "sphincs": {
            "public_key": hex::encode(slh_pub.into_bytes()),
            "signature": hex::encode(slh_sig),
        }
    });

    fs::write("pqc_test_vectors.json", serde_json::to_string_pretty(&vectors).unwrap())
        .expect("write file");
    println!("Zapisano pqc_test_vectors.json");
}
