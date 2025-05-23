# Iu-ventus - Social Platform to allow students being hired
A Flask-based social platform connecting students and businesses, it supports posts, comments, user profiles, notifications, and administrative controls

## Features
- **User Roles**  
  `Student` | `Business` | `Admin`
- **Authentication**  
  Signup/Login with email verification, password reset, and persistent sessions
- **Profile Management**  
  - Students: CV upload, skill tags, social links  
  - Businesses: Address, phone, tags  
  - Profile pictures and bio for all users
- **Content**  
  - Create posts with images and tags  
  - Add/delete comments  
  - Search posts by content/title/tags
- **Connections**  
  - Send contact requests  
  - Accept/reject notifications
- **Admin Tools**  
  - View all users  
  - Delete accounts with email notifications

## Installation
### Requirements
- Python 3.9+
- MariaDB database
- SMTP server (e.g., Gmail)
