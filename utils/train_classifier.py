"""
utils/train_classifier.py — PHASE 2: Fine-tune MobileNetV2 on your own
vehicle photos to enable real make/model recognition.

WHY THIS IS NEEDED
------------------
There is no public, ready-made "Nigerian common cars" classifier. To get
real make/model predictions (not just colour, which works out of the box),
you need to fine-tune a model on labelled photos of the specific cars you
care about. This script does that with transfer learning on MobileNetV2,
which is small and fast enough to train on a normal laptop CPU (no GPU
required) for a handful of classes and a few dozen photos per class.

HOW TO USE
----------
1. Create folders under training_data/, one per class, named
   "Make_Model" (use underscores, no spaces), e.g.:

       training_data/
         Toyota_Camry/     20-50+ jpg/png photos of Toyota Camrys
         Honda_Accord/     20-50+ jpg/png photos of Honda Accords
         Lexus_RX350/      20-50+ jpg/png photos of Lexus RX350s
         Mercedes_C-Class/ ...
         Hyundai_Elantra/  ...

   Tips for good results:
     - Use varied angles, lighting, and colours per class.
     - At least ~30 photos per class is a reasonable starting point for
       a school project demo; more is better.
     - Keep photos reasonably cropped around the vehicle (not tiny in a
       huge background) for the best accuracy.

2. Install training dependencies (already in requirements.txt):
       pip install tensorflow-cpu pillow

3. Run:
       python utils/train_classifier.py

   This will:
     - Build a MobileNetV2 backbone (ImageNet weights, frozen) + a new
       trainable classification head sized to your number of classes.
     - Train for a few epochs on your training_data/ folder (80/20
       train/validation split).
     - Save the trained model to models_ml/vehicle_classifier.h5 and the
       class-index-to-label mapping to models_ml/class_labels.json.

4. Restart the Flask app. utils/recognition.py automatically detects and
   loads the trained model on next use -- no code changes needed.

NOTE: the first run downloads MobileNetV2's ImageNet weights (~14 MB),
so you'll need an internet connection the first time you train.
"""

import json
import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TRAINING_DATA_DIR = os.path.join(BASE_DIR, "training_data")
MODEL_OUTPUT_DIR = os.path.join(BASE_DIR, "models_ml")
MODEL_OUTPUT_PATH = os.path.join(MODEL_OUTPUT_DIR, "vehicle_classifier.h5")
LABELS_OUTPUT_PATH = os.path.join(MODEL_OUTPUT_DIR, "class_labels.json")

IMG_SIZE = (224, 224)
BATCH_SIZE = 16
EPOCHS = 12


def main():
    import tensorflow as tf
    from tensorflow.keras.applications import MobileNetV2
    from tensorflow.keras.applications.mobilenet_v2 import preprocess_input
    from tensorflow.keras.layers import GlobalAveragePooling2D, Dense, Dropout
    from tensorflow.keras.models import Model
    from tensorflow.keras.preprocessing.image import ImageDataGenerator

    if not os.path.isdir(TRAINING_DATA_DIR) or not os.listdir(TRAINING_DATA_DIR):
        print(
            f"No training data found in {TRAINING_DATA_DIR}.\n"
            "Create one sub-folder per class (e.g. training_data/Toyota_Camry/) "
            "with photos, then re-run this script. See the module docstring "
            "at the top of this file for details."
        )
        return

    class_dirs = sorted(
        d for d in os.listdir(TRAINING_DATA_DIR)
        if os.path.isdir(os.path.join(TRAINING_DATA_DIR, d))
    )
    num_classes = len(class_dirs)
    print(f"Found {num_classes} classes: {class_dirs}")

    if num_classes < 2:
        print("Need at least 2 classes (folders) to train a classifier.")
        return

    datagen = ImageDataGenerator(
        preprocessing_function=preprocess_input,
        validation_split=0.2,
        rotation_range=15,
        width_shift_range=0.1,
        height_shift_range=0.1,
        zoom_range=0.15,
        horizontal_flip=True,
    )

    train_gen = datagen.flow_from_directory(
        TRAINING_DATA_DIR,
        target_size=IMG_SIZE,
        batch_size=BATCH_SIZE,
        class_mode="categorical",
        subset="training",
    )
    val_gen = datagen.flow_from_directory(
        TRAINING_DATA_DIR,
        target_size=IMG_SIZE,
        batch_size=BATCH_SIZE,
        class_mode="categorical",
        subset="validation",
    )

    # class_indices maps label -> index; invert it for prediction time
    index_to_label = {v: k for k, v in train_gen.class_indices.items()}
    ordered_labels = [index_to_label[i] for i in range(num_classes)]

    base_model = MobileNetV2(
        input_shape=(*IMG_SIZE, 3),
        include_top=False,
        weights="imagenet",
    )
    base_model.trainable = False  # freeze backbone for fast CPU training

    x = base_model.output
    x = GlobalAveragePooling2D()(x)
    x = Dense(128, activation="relu")(x)
    x = Dropout(0.3)(x)
    predictions = Dense(num_classes, activation="softmax")(x)

    model = Model(inputs=base_model.input, outputs=predictions)
    model.compile(optimizer="adam", loss="categorical_crossentropy", metrics=["accuracy"])

    print(model.summary())

    model.fit(
        train_gen,
        validation_data=val_gen,
        epochs=EPOCHS,
    )

    os.makedirs(MODEL_OUTPUT_DIR, exist_ok=True)
    model.save(MODEL_OUTPUT_PATH)
    with open(LABELS_OUTPUT_PATH, "w") as f:
        json.dump(ordered_labels, f, indent=2)

    print(f"\nSaved trained model to {MODEL_OUTPUT_PATH}")
    print(f"Saved class labels to {LABELS_OUTPUT_PATH}")
    print("Restart the Flask app to start using real make/model recognition.")


if __name__ == "__main__":
    main()
