import time

from rfid_reader import Reader


def main():
    reader = Reader()
    print("=" * 60)
    print("RFID Diagnostic Reader")
    print("Hold a programmed tag near the reader to display its contents.")
    print("Press Ctrl+C to exit.")
    print("=" * 60)

    try:
        while True:
            reader.read_tag()
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nExiting diagnostic reader.")
    finally:
        reader.cleanup()


if __name__ == "__main__":
    main()
