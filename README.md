# Plex Auto Languages

Plex Auto Languages enhances your Plex experience by automatically updating the audio and subtitle settings of TV shows based on your preferences. Similar to Netflix, it remembers your language preferences for each TV show without interfering with your global settings or other users' preferences.

## Features

- **Seamless Language Selection**: Watch *Squid Game* in Korean with English subtitles? Just set it once for the first episode and enjoy the rest of the series hassle-free. 👌
- **Per-Show Customization**: Want *The Mandalorian* in English and *Game of Thrones* in French? Preferences are tracked separately for each show. ✔️
- **Multi-User Support**: Perfect for households with diverse preferences. Each user gets their tracks automatically and independently selected. ✔️

---

## Getting Started

### Requirements

To use Plex Auto Languages, you'll need:
1. **Plex Token**: Learn how to retrieve yours from the [official Plex guide](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/).
2. **Python 3.8+** or **Docker**: The application can run natively via Python or as a Docker container.

---

## Installation Options

### Docker Installation

Running Plex Auto Languages with Docker is the recommended approach.

#### Docker Image Tags

The Docker image is available in three tag formats:

- **`main` (Development)**: Tracks the latest commit on the main branch. Includes the newest features but may be unstable.
  - *Recommended for*: Developers and testers.
  - *Note*: Updates with every new commit; may include breaking changes.

- **`latest` (Stable Release)**: Points to the most recent stable release. Ideal for production environments.
  - *Recommended for*: General use.

- **`A.B.C.D` (Versioned Releases)**: Specific version tags for consistency and reliability.
  - *Recommended for*: Environments requiring version control.

#### Installation Options

The Docker image can be pulled from either of the following registries:
- `ghcr.io/journeydocker/plex-auto-languages:<tagname>`
- `journeyover/plex-auto-languages:<tagname>`

#### Docker Compose Configuration

Here’s an example of a minimal `docker-compose.yml` setup:

```yaml
docker-compose:
version: "3"
services:
  plexautolanguages:
    image: journeyover/plex-auto-languages:main
    environment:
      - PLEX_URL=http://plex:32400
      - PLEX_TOKEN=MY_PLEX_TOKEN
      - TZ=Europe/Paris
    volumes:
      - ./config:/config
```

#### Run with Docker CLI

Alternatively, you can run the container directly:
```bash
docker run -d \
  -e PLEX_URL=http://plex:32400 \
  -e PLEX_TOKEN=MY_PLEX_TOKEN \
  -e TZ=Europe/Paris \
  -v ./config:/config \
  journeyover/plex-auto-languages:main
```

### Python Installation

#### Steps:

1. **Clone the Repository**:
   ```bash
   git clone git@github.com:JourneyDocker/Plex-Auto-Languages.git
   ```
2. **Install Dependencies**:
   ```bash
   cd Plex-Auto-Languages
   python3 -m pip install -r requirements.txt
   ```
3. **Create Configuration File**:
   Use the template in the [default configuration file](https://github.com/JourneyDocker/Plex-Auto-Languages/blob/main/config.example.yaml) to create your own `config.yaml`. Only `plex.url` and `plex.token` are required.

4. **Run the Application**:
   ```bash
   python3 main.py -c ./config.yaml
   ```

---

## Configuration

The application can be configured with either:
- **Environment Variables**
- **YAML File** (mounted in `/config/config.yaml`)

### Key Parameters

#### Plex Configuration
```yaml
plex:
  url: "http://plex:32400"  # Required: Plex server URL
  token: "MY_PLEX_TOKEN"    # Required: Plex Token
```

#### Update Settings
```yaml
plexautolanguages:
  update_level: "show"       # Options: "show" (default), "season"
  update_strategy: "all"     # Options: "all" (default), "next"
  trigger_on_play: true       # Update language when playing an episode
  trigger_on_scan: true       # Update language when new files are scanned
  trigger_on_activity: false  # Update language when navigating Plex (experimental)
```

#### Notifications (Optional)
Configure notifications with [Apprise](https://github.com/caronc/apprise):
```yaml
notifications:
  enable: true
  apprise_configs:
    - "discord://webhook_id/webhook_token"
```

#### Advanced Options
```yaml
scheduler:
  enable: true
  schedule_time: "04:30"
data_path: ""  # Path for system/cache files
debug: false    # Enable debug logs
```

---

## License

This project is licensed under the [MIT License](LICENSE).
