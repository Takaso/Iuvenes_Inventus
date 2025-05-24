# Iu-ventus (Iuvenes Inventus) — Social Hiring Platform for Students and Businesses

A Flask-based italian social platform that connects students and businesses, allowing them to create posts, comment, manage profiles, send contact requests, and much more. Designed with three user roles (Student, Business, Admin) and a rich feature set to streamline opportunities and professional networking.

---

## Table of Contents

1. [Features](#features)  
2. [Architecture & Tech Stack](#architecture--tech-stack)  
3. [Getting Started](#getting-started)  
   - [Prerequisites](#prerequisites)  
   - [Installation](#installation)  
   - [Configuration](#configuration)  
   - [Database Setup](#database-setup)  
   - [Running the App](#running-the-app)  
4. [Usage](#usage)  
   - [Authentication Flow](#authentication-flow)  
   - [Profile Management](#profile-management)  
   - [Creating & Managing Posts](#creating--managing-posts)  
   - [Comments & Notifications](#comments--notifications)  
   - [Search & Discovery](#search--discovery)  
   - [Connections & Messaging](#connections--messaging)  
   - [Admin Controls](#admin-controls)  
5. [Interface Examples](#interface-examples)  
   - [Default Landing Page](#default-landing-page)  
   - [User Profile Page](#user-profile-page)  
   - [Homepage / Feed](#homepage--feed)  
6. [Roadmap & To Do](#roadmap--to-do)  
7. [Contributing](#contributing)  
8. [License](#license)  

---

## Features

- **User Roles**  
  - **Student**: Upload CV, select skill tags, add social links  
  - **Business**: List address & phone, select industry tags 
  - **Admin**: Review business-verification requests, view/delete any user

- **Authentication**  
  - Email/password signup & login  
  - Email verification with 6-digit code (expires in 30 min)  
  - “Remember me” persistent sessions (30 days)  
  - Password reset via email code

- **Profile Management**  
  - Update bio, username, profile picture  
  - Upload CV (PDF) for students  
  - Add up to 3 skill/industry tags
  - Link LinkedIn, GitHub, personal website, YouTube

- **Content & Interaction**  
  - Create posts with title, content, optional image, and up to 5 tags  
  - Comment on posts; post owners receive notification  
  - Search posts by title/content/tags  
  - Search users by username or tags (scored & ranked)

- **Connections & Messaging**  
  - Send contact requests with custom message  
  - Accept/reject with optional notification email  
  - Private chat interface for connected users

- **Notifications**  
  - In-app notifications for comments, requests, verification updates  
  - Unread count badge in navbar  
  - Email alerts for critical events (verification approved, connection accepted)

- **Admin Tools**  
  - Pending business-verification queue  
  - Approve/reject requests with auto-notifications  
  - View all users and delete accounts (optional email with reason)

---

## Architecture & Tech Stack

- **Backend**: Python 3.9+, Flask  
- **Database**: MariaDB (via `mariadb` Python driver)  
- **Authentication & Security**:  
  - Password hashing: `bcrypt`  
  - Email validation: `email_validator`  
  - Session management: Flask’s secure cookies  
- **Email**: SMTP via `smtplib`, HTML & plain-text emails  
- **Image Handling**: Pillow (PIL) for uploads & thumbnails  
- **Templating**: Jinja2, custom filters (e.g., `datetimeformat`) 
- **Interface**: Tailwind.css 
- **Static Files**: Stored under `/static/uploads` with secure filenames  

---

## Getting Started

### Prerequisites

- Python 3.9 or newer  
- MariaDB server  
- SMTP account (e.g., Gmail) for sending verification & notification emails  

### Installation

1. **Clone the repo**  
   ```bash
   git clone https://github.com/yourusername/iu-ventus.git
   cd iu-ventus
   ```

2. **Set up virtual environment & install dependencies**

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

### Configuration

Copy `config.example.json` to `config.json` and populate with your credentials:

```json
{
  "sql_host": "localhost",
  "sql_user": "iuventus_user",
  "sql_password": "your_db_password",
  "sql_database": "iuventus",
  "smtp_server": "smtp.gmail.com",
  "smtp_port": 587,
  "smtp_user": "your-email@gmail.com",
  "smtp_password": "your-email-password"
}
```

### Database Setup

1. Create the MariaDB database and user:

   ```sql
   CREATE DATABASE iuventus;
   CREATE USER 'iuventus_user'@'localhost' IDENTIFIED BY 'your_db_password';
   GRANT ALL PRIVILEGES ON iuventus.* TO 'iuventus_user'@'localhost';
   ```
2. Run the schema SQL (in `/db/schema.sql`):

   ```bash
   mysql -u iuventus_user -p iuventus < db/schema.sql
   ```

### Running the App

```bash
export FLASK_APP=main.py
flask run --reload
```

Visit `http://localhost:5000` in your browser

---

## Usage

### Authentication Flow

1. **Signup**: choose Student or Business, enter email, password, optional username
2. **Email Verification**: enter 6-digit code emailed to you
3. **Business Verification**: Businesses submit additional details; Admin reviews

### Profile Management

* Accessible under **My Profile** menu
* Update bio, upload profile picture (thumbnail auto-generated), edit social links
* Students: upload CV (PDF) and select skill tags.
* Businesses: provide address & phone, select industry tags

### Creating & Managing Posts

* **New Post** button on homepage.
* Enter title (max 100 chars), content, optional image (auto-thumbnail), comma-separated tags (max 5)
* Delete your own posts from the post card menu

### Comments & Notifications

* Comment box under each post
* Post owner sees in-app notification and optional email
* Manage notifications in **Notifications** panel (accept/reject requests)

### Search & Discovery

* Toggle between **Posts** and **Users** search in navbar
* Posts: search by title, content, or tags
* Users: search by username or tags; results scored & sorted by relevance

### Connections & Messaging

* On a user's profile, click **Send Contact Request** and add message
* Receiver sees request in notifications; can accept/reject
* Upon acceptance, a private chat appears under **Messages**

### Admin Controls

* **Admin Verifications**: list of pending business verifications; approve/reject
* **View Database**: list all users; delete any account with optional email reason
* All admin actions send system notifications and emails as appropriate

---

## Interface Examples

### Default Landing Page

![image](https://github.com/user-attachments/assets/03da5846-3da9-488d-ad39-04ed4dbdf90d)

> **How it works:**
>
> * Shows login/sign-up prompt if unauthenticated
> * After login, redirects to the personalized homepage/feed

### User Profile Page

![image](https://github.com/user-attachments/assets/1bb046d4-baa4-4ed3-86d4-5149b0fca917)
![image](https://github.com/user-attachments/assets/0a5dfa2a-6a3f-4d82-9ed4-3cb638cbb76d)

> **How it works:**
>
> * Displays user's avatar, bio, and social links
> * Editable fields for current user; read-only for others
> * Students: CV download link, skill tags
> * Businesses: address & phone, industry tags
> * **Send Contact Request** button appears when viewing another user

![image](https://github.com/user-attachments/assets/b4d0b6ac-dd18-4d26-a45a-f6d083604f0f)

### Homepage / Feed

![image](https://github.com/user-attachments/assets/8f036960-cbd4-41fb-b89e-9d6b7242ee35)

> **How it works:**
>
> * Shows relevant posts: personalized by your tags or global if no tags
> * Post cards include author info, timestamp (formatted via Jinja filter), tags, image thumbnail, like/comment buttons
> * Sidebar suggests other users to connect with (alternating Student/Business based on your role)

---

## To Do's

* **Rich Text Editor** for posts (markdown support)
* **Real-time Notifications and Messages** with WebSockets
* **Like/Upvote System** for posts and comments
* **Mobile Responsive UI** improvements
* **User recommendation algorithm** for employement

---

## Contributing

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/YourFeature`)
3. Commit your changes (`git commit -m "Add YourFeature"`)
4. Push to branch (`git push origin feature/YourFeature`)
5. Open a Pull Request

---

## License

This project is licensed under the MIT License
