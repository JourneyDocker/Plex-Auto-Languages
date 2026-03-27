# Plex Auto Languages

Plex Auto Languages enhances your Plex experience by automatically updating the audio and subtitle settings of TV shows based on your preferences. Similar to Netflix, it remembers your language settings for each TV show without interfering with your global settings or other users' preferences.

## Features

- **Seamless Language Selection**:
  Watch *Squid Game* in Korean with English subtitles? Set it once for the first episode and enjoy the rest of the series hassle-free. 👌

- **Per-Show Customization**:
  Want *The Mandalorian* in English and *Game of Thrones* in French? Preferences are tracked separately for each show. ✔️

- **Multi-User Support**:
  Perfect for households with diverse preferences. Each user gets their tracks automatically and independently selected. ✔️

## Getting Started

### Requirements

To use Plex Auto Languages, you'll need:

1. **Plex Token**:
   Learn how to retrieve yours from the [official Plex guide](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/).

2. **Python 3.8+** or **Docker**:
   The application can run natively via Python or as a Docker container.

---

### Installation Options

#### Docker Installation

Running Plex Auto Languages with Docker is the recommended approach.

**Docker Image Tags:**

- **`main` (Development)**:
  Tracks the latest commit on the main branch. Includes the newest features but may be unstable.

  *Recommended for*: Developers and testers.

  *Note*: Updates with every commit; may include breaking changes.

- **`latest` (Stable Release)**:
  Points to the most recent stable release. Ideal for production environments.

  *Recommended for*: General use.

- **`A.B.C.D` (Versioned Releases)**:
  Specific version tags for consistency and reliability.

  *Recommended for*: Environments requiring strict version control.

**Docker Registries:**

The Docker image can be pulled from either of the following registries:
- `ghcr.io/journeydocker/plex-auto-languages:<tagname>`
- `journeyover/plex-auto-languages:<tagname>`

**Docker Compose Configuration:**

Here's an example of a minimal `docker-compose.yml` setup:

```yaml
services:
  plexautolanguages:
    image: journeyover/plex-auto-languages:latest
    environment:
      - PLEX_URL=http://plex:32400
      - PLEX_TOKEN=MY_PLEX_TOKEN
      - TZ=Europe/Paris
    volumes:
      - ./config:/config
```

**Run with Docker CLI:**

Alternatively, you can run the container directly:

```bash
docker run -d \
  -e PLEX_URL=http://plex:32400 \
  -e PLEX_TOKEN=MY_PLEX_TOKEN \
  -e TZ=Europe/Paris \
  -v ./config:/config \
  journeyover/plex-auto-languages:latest
```

-----

#### Python Installation

Follow these steps for a native Python setup:

1.  **Clone the Repository**:

    ```bash
    git clone https://github.com/JourneyDocker/Plex-Auto-Languages.git
    ```

2.  **Install Dependencies**:

    ```bash
    cd Plex-Auto-Languages
    python -m pip install -r requirements.txt
    ```

3.  **Create Configuration File**:

    Use the template in the [default configuration file](https://github.com/JourneyDocker/Plex-Auto-Languages/blob/main/config.example.yaml) to create your own `config.yaml`. Only `plex.url` and `plex.token` are required.

4.  **Run the Application**:

    ```bash
    python main.py -c ./config.yaml
    ```

-----

### How to Update

#### Updating Docker

If you are running the Docker container, update to the latest version by pulling the new image and recreating your container:

1.  **Pull the latest image**:
    ```bash
    docker pull journeyover/plex-auto-languages:latest
    ```
2.  **Recreate the container**: Stop your current container and start it again using your existing `docker-compose up -d` or `docker run` command.

#### Updating Python

To update a native Python installation to the latest version:

1.  **Pull the latest changes**:

    ```bash
    git pull
    ```

2.  **Update dependencies** (if requirements.txt has changed):

    ```bash
    python -m pip install -r requirements.txt
    ```

3.  **Review your configuration**:
    Compare your `config.yaml` with the latest [config.example.yaml](https://github.com/JourneyDocker/Plex-Auto-Languages/blob/main/config.example.yaml) and add any new settings as needed.

4.  **Restart the application**:
    Restart PAL with your updated code and configuration.

If you're migrating from an older version, consider backing up your config and following the installation steps from scratch.

## Configuration

The application can be configured using either:

  - **Environment Variables**
  - **YAML File** (mounted at `/config/config.yaml`; see [config.example.yaml](https://github.com/JourneyDocker/Plex-Auto-Languages/blob/main/config.example.yaml) for example config)

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
  update_level: "show"          # Options: "show" (default), "season"
  update_strategy: "next"       # Options: "all", "next" (default)
  trigger_on_play: true         # Update language when playing an episode
  trigger_on_scan: true         # Update language when new files are scanned
  trigger_on_activity: false    # Update language when navigating Plex (experimental)
  refresh_library_on_scan: true # Refresh cached library on Plex scans
  ignore_labels:                # Ignore shows with these Plex labels
    - PAL_IGNORE
  ignore_libraries:             # Ignore these libraries when updating sub/audio language
    - ""
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
  schedule_time: "02:00"
data_path: ""  # Path for system/cache files
debug: false   # Enable debug logs
```

### Environment Variable Summary

| Environment Variable            | Default Value | Description                                                                                                                  |
| ------------------------------- | ------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `PLEX_URL`                      | *(none)*      | URL to your Plex server. Replace `http://plex:32400` with your actual Plex server URL.                                       |
| `PLEX_TOKEN`                    | *(none)*      | Plex authentication token.                                                                                                   |
| `UPDATE_LEVEL`                  | `show`        | Determines whether the update applies to the entire show or just the current season. Accepted values: `show`, `season`.      |
| `UPDATE_STRATEGY`               | `next`        | Chooses whether to update all episodes or only the next one. Accepted values: `all`, `next`.                                 |
| `TRIGGER_ON_PLAY`               | `true`        | If set to true, playing an episode triggers a language update.                                                               |
| `TRIGGER_ON_SCAN`               | `true`        | If set to true, scanning for new files triggers a language update.                                                           |
| `TRIGGER_ON_ACTIVITY`           | `false`       | If set to true, browsing the Plex library triggers a language update.                                                        |
| `REFRESH_LIBRARY_ON_SCAN`       | `true`        | Refreshes the cached library when the Plex server scans its library.                                                         |
| `IGNORE_LABELS`                 | `PAL_IGNORE`  | Comma-separated list of Plex labels. Shows with these labels will be ignored.                                                |
| `IGNORE_LIBRARIES`              | *(none)*      | Comma-separated list of library names that PAL will ignore when updating subtitle/audio languages.                           |
| `SCHEDULER_ENABLE`              | `true`        | Enables or disables the scheduler feature.                                                                                   |
| `SCHEDULER_SCHEDULE_TIME`       | `02:00`       | Time (in `HH:MM` format) when the scheduler starts its task.                                                                 |
| `NOTIFICATIONS_ENABLE`          | `false`       | Enables or disables notifications.                                                                                           |
| `NOTIFICATIONS_APPRISE_CONFIGS` | `[]`          | JSON array of Apprise notification configurations. See Apprise docs for more information: https://github.com/caronc/apprise. |
| `DEBUG`                         | `false`       | Enables debug mode for verbose logging.                                                                                      |

> [!NOTE]
>
>   * **Docker Secrets:** The Plex Token and Plex URL can be provided as Docker secrets. Specify their filepaths using `PLEX_TOKEN_FILE` (defaults to `/run/secrets/plex_token`) and `PLEX_URL_FILE` (defaults to `/run/secrets/plex_url`).
>   * **Apprise Configs:** The `NOTIFICATIONS_APPRISE_CONFIGS` variable should be a JSON string representing an array of notification configurations. Each can include `urls`, `users`, and `events`. Example:
>     ```json
>     [
>       {"urls": ["discord://webhook_id/webhook_token"]},
>       {"urls": ["gotify://hostname/token"], "users": ["MyUser1", "MyUser2"]},
>       {"urls": ["tgram://bottoken/ChatID"], "users": ["MyUser3"], "events": ["play_or_activity"]}
>     ]
>     ```

## License

This project is licensed under the [MIT License](LICENSE).
