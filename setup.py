import subprocess
import sys
import nltk

def install_requirements():
    print("Installing requirements...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

def download_nltk_data():
    print("Downloading NLTK data...")
    nltk.download('punkt')
    nltk.download('stopwords')

def main():
    try:
        install_requirements()
        download_nltk_data()
        print("\nSetup completed successfully!")
        print("\nYou can now run the scraper using:")
        print("python main.py --team-id \"teamXYZ\" --urls \"https://example.com/blog\" --output \"output.json\"")
    except Exception as e:
        print(f"Error during setup: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 