/*M!999999\- enable the sandbox mode */ 
-- MariaDB dump 10.19-11.6.2-MariaDB, for Win64 (AMD64)
--
-- Host: localhost    Database: isucaufafms_capstone_project_db
-- ------------------------------------------------------
-- Server version	11.6.2-MariaDB

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*M!100616 SET @OLD_NOTE_VERBOSITY=@@NOTE_VERBOSITY, NOTE_VERBOSITY=0 */;

--
-- Table structure for table `access_session`
--

DROP TABLE IF EXISTS `access_session`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `access_session` (
  `session_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `token_id` varchar(255) NOT NULL,
  `ip_address` char(39) NOT NULL,
  `device_info` varchar(255) DEFAULT NULL,
  `issued_at` datetime(6) NOT NULL,
  `expires_at` datetime(6) NOT NULL,
  `revoked_at` datetime(6) DEFAULT NULL,
  `session_status` varchar(50) NOT NULL,
  `user_id_FK` int(11) NOT NULL,
  `last_verified_location` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL,
  `session_policy` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL,
  `trusted_device` tinyint(1) NOT NULL,
  `last_activity_at` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`session_id_PK`),
  UNIQUE KEY `token_id` (`token_id`),
  KEY `ACCESS_SESSION_user_id_FK_525a0de2_fk_OFFICER_USER_user_id_PK` (`user_id_FK`)
) ENGINE=InnoDB AUTO_INCREMENT=163 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `aid_set_asides`
--

DROP TABLE IF EXISTS `aid_set_asides`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `aid_set_asides` (
  `setaside_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `aid_type` varchar(20) NOT NULL,
  `amount` decimal(10,2) NOT NULL,
  `amount_released` decimal(10,2) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `aid_tracking_post_id_FK` int(11) DEFAULT NULL,
  `assessment_item_id_FK` int(11) NOT NULL,
  `fund_transaction_id_FK` int(11) NOT NULL,
  `member_assessment_id_FK` int(11) NOT NULL,
  `pooled_after_release` tinyint(1) NOT NULL,
  PRIMARY KEY (`setaside_id_PK`),
  UNIQUE KEY `aid_set_asides_member_assessment_id_FK__eb28f5be_uniq` (`member_assessment_id_FK`,`assessment_item_id_FK`),
  KEY `aid_set_asides_aid_tracking_post_id_81b239a5_fk_aid_track` (`aid_tracking_post_id_FK`),
  KEY `aid_set_asides_assessment_item_id_F_47bba06d_fk_assessmen` (`assessment_item_id_FK`),
  KEY `aid_set_asides_fund_transaction_id__bf2b67ae_fk_fund_tran` (`fund_transaction_id_FK`),
  KEY `aid_set_asi_aid_typ_26322f_idx` (`aid_type`,`aid_tracking_post_id_FK`),
  CONSTRAINT `aid_set_asides_aid_tracking_post_id_81b239a5_fk_aid_track` FOREIGN KEY (`aid_tracking_post_id_FK`) REFERENCES `aid_tracking_post` (`post_id_PK`),
  CONSTRAINT `aid_set_asides_assessment_item_id_F_47bba06d_fk_assessmen` FOREIGN KEY (`assessment_item_id_FK`) REFERENCES `assessment_items` (`item_id_PK`),
  CONSTRAINT `aid_set_asides_fund_transaction_id__bf2b67ae_fk_fund_tran` FOREIGN KEY (`fund_transaction_id_FK`) REFERENCES `fund_transaction` (`transaction_id_PK`),
  CONSTRAINT `aid_set_asides_member_assessment_id_8d1e4596_fk_member_as` FOREIGN KEY (`member_assessment_id_FK`) REFERENCES `member_assessments` (`member_assessment_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=525 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `aid_tracking_post`
--

DROP TABLE IF EXISTS `aid_tracking_post`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `aid_tracking_post` (
  `post_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `aid_type` varchar(50) NOT NULL,
  `target_month` varchar(7) NOT NULL,
  `total_expected` decimal(10,2) NOT NULL,
  `total_collected` decimal(10,2) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `notes` longtext NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `archive_id_FK` int(11) NOT NULL,
  `created_by_user_id_FK` int(11) DEFAULT NULL,
  `source_id` int(11) DEFAULT NULL,
  `source_type` varchar(50) DEFAULT NULL,
  `status` varchar(20) NOT NULL,
  `finish_skip_remaining` tinyint(1) NOT NULL,
  `finish_status` varchar(20) NOT NULL,
  `finish_paid_with_funds` tinyint(1) NOT NULL,
  `deduction_sheet` varchar(100) DEFAULT NULL,
  `deduction_batch_reference` varchar(100) NOT NULL,
  `deduction_payroll_period` varchar(50) NOT NULL,
  `deduction_sheet_uploaded_at` datetime(6) DEFAULT NULL,
  `deduction_remitted_amount` decimal(10,2) DEFAULT NULL,
  `deduction_remitted_at` datetime(6) DEFAULT NULL,
  `deduction_remitted_date` date DEFAULT NULL,
  `deduction_remittance_reference` varchar(100) NOT NULL,
  `finish_cycle` smallint(5) unsigned NOT NULL,
  `collection_started` tinyint(1) NOT NULL DEFAULT 0,
  `assessment_item_id_FK` int(11) DEFAULT NULL,
  `external_campus` varchar(120) DEFAULT NULL,
  `external_beneficiary` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`post_id_PK`),
  KEY `AID_TRACKING_POST_archive_id_FK_2bff15c8_fk_transacti` (`archive_id_FK`),
  KEY `AID_TRACKING_POST_created_by_user_id_F_a3a13677_fk_OFFICER_U` (`created_by_user_id_FK`),
  KEY `aid_tracking_post_assessment_item_id_F_39c09b31_fk_assessmen` (`assessment_item_id_FK`),
  CONSTRAINT `aid_tracking_post_assessment_item_id_F_39c09b31_fk_assessmen` FOREIGN KEY (`assessment_item_id_FK`) REFERENCES `assessment_items` (`item_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `album`
--

DROP TABLE IF EXISTS `album`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `album` (
  `album_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `title` varchar(255) NOT NULL,
  `description` longtext NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `created_by_id` int(11) DEFAULT NULL,
  `event_id` int(11) DEFAULT NULL,
  `cover_photo_id` int(11) DEFAULT NULL,
  PRIMARY KEY (`album_id_PK`),
  KEY `ALBUM_created_by_id_8df7d8ed_fk_OFFICER_USER_user_id_PK` (`created_by_id`),
  KEY `ALBUM_event_id_160d77b2_fk_EVENT_event_id_PK` (`event_id`),
  KEY `ALBUM_cover_photo_id_c5b9d95a_fk_PHOTO_photo_id_PK` (`cover_photo_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `announcement`
--

DROP TABLE IF EXISTS `announcement`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `announcement` (
  `announcement_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `title` varchar(255) NOT NULL,
  `category` varchar(50) NOT NULL,
  `description` longtext NOT NULL,
  `attachment_path` varchar(500) NOT NULL,
  `attachment_name` varchar(255) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `published_at` datetime(6) NOT NULL,
  `expiry_date` datetime(6) DEFAULT NULL,
  `published_by_user_id_FK` int(11) DEFAULT NULL,
  `image` varchar(100) DEFAULT NULL,
  PRIMARY KEY (`announcement_id_PK`),
  KEY `ANNOUNCEMENT_published_by_user_id_1867ecbe_fk_OFFICER_U` (`published_by_user_id_FK`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `announcement_category`
--

DROP TABLE IF EXISTS `announcement_category`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `announcement_category` (
  `category_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`category_id_PK`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `assessment_items`
--

DROP TABLE IF EXISTS `assessment_items`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `assessment_items` (
  `item_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `purpose` varchar(100) NOT NULL,
  `amount` decimal(10,2) NOT NULL,
  `recipient` varchar(255) DEFAULT NULL,
  `notes` longtext DEFAULT NULL,
  `priority_order` int(11) NOT NULL,
  `assessment_id_FK` int(11) NOT NULL,
  `custom_label` varchar(100) DEFAULT NULL,
  `recipient_type` varchar(20) NOT NULL,
  `external_campus` varchar(120) DEFAULT NULL,
  `external_beneficiary` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`item_id_PK`),
  KEY `assessment_items_assessment_id_FK_e8a67355_fk_monthly_a` (`assessment_id_FK`),
  CONSTRAINT `assessment_items_assessment_id_FK_e8a67355_fk_monthly_a` FOREIGN KEY (`assessment_id_FK`) REFERENCES `monthly_assessments` (`assessment_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=24 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `attendance`
--

DROP TABLE IF EXISTS `attendance`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `attendance` (
  `attendance_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `date` date NOT NULL,
  `check_in_time` time(6) DEFAULT NULL,
  `check_out_time` time(6) DEFAULT NULL,
  `status` varchar(20) NOT NULL,
  `check_in_method` varchar(20) NOT NULL,
  `member_id_FK` int(11) NOT NULL,
  `event_id_FK` int(11) DEFAULT NULL,
  PRIMARY KEY (`attendance_id_PK`),
  KEY `ATTENDANCE_member_id_FK_977d6132_fk_MEMBER_member_id_PK` (`member_id_FK`),
  KEY `ATTENDANCE_event_id_FK_1fe0a37c_fk_EVENT_event_id_PK` (`event_id_FK`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `audit_findings_report`
--

DROP TABLE IF EXISTS `audit_findings_report`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `audit_findings_report` (
  `audit_report_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `report_title` varchar(255) NOT NULL,
  `report_period` varchar(100) NOT NULL,
  `findings_summary` longtext NOT NULL,
  `report_status` varchar(50) NOT NULL,
  `prepared_date` date NOT NULL,
  `board_submission_date` date DEFAULT NULL,
  `board_meeting_reference` varchar(255) DEFAULT NULL,
  `presentation_status` varchar(50) NOT NULL,
  `certification_status` varchar(50) NOT NULL,
  `certified_by_user_id_FK` int(11) DEFAULT NULL,
  `prepared_by_user_id_FK` int(11) NOT NULL,
  PRIMARY KEY (`audit_report_id_PK`),
  KEY `AUDIT_FINDINGS_REPOR_certified_by_user_id_d3493449_fk_OFFICER_U` (`certified_by_user_id_FK`),
  KEY `AUDIT_FINDINGS_REPOR_prepared_by_user_id__537aa0f1_fk_OFFICER_U` (`prepared_by_user_id_FK`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `auth_group`
--

DROP TABLE IF EXISTS `auth_group`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `auth_group` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(150) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `auth_group_permissions`
--

DROP TABLE IF EXISTS `auth_group_permissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `auth_group_permissions` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `group_id` int(11) NOT NULL,
  `permission_id` int(11) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `auth_group_permissions_group_id_permission_id_0cd325b0_uniq` (`group_id`,`permission_id`),
  KEY `auth_group_permissio_permission_id_84c5c92e_fk_auth_perm` (`permission_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `auth_permission`
--

DROP TABLE IF EXISTS `auth_permission`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `auth_permission` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `content_type_id` int(11) NOT NULL,
  `codename` varchar(100) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `auth_permission_content_type_id_codename_01ab375a_uniq` (`content_type_id`,`codename`)
) ENGINE=InnoDB AUTO_INCREMENT=301 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `auth_user`
--

DROP TABLE IF EXISTS `auth_user`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `auth_user` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `password` varchar(128) NOT NULL,
  `last_login` datetime(6) DEFAULT NULL,
  `is_superuser` tinyint(1) NOT NULL,
  `username` varchar(150) NOT NULL,
  `first_name` varchar(150) NOT NULL,
  `last_name` varchar(150) NOT NULL,
  `email` varchar(254) NOT NULL,
  `is_staff` tinyint(1) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `date_joined` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `auth_user_groups`
--

DROP TABLE IF EXISTS `auth_user_groups`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `auth_user_groups` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL,
  `group_id` int(11) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `auth_user_groups_user_id_group_id_94350c0c_uniq` (`user_id`,`group_id`),
  KEY `auth_user_groups_group_id_97559544_fk_auth_group_id` (`group_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `auth_user_user_permissions`
--

DROP TABLE IF EXISTS `auth_user_user_permissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `auth_user_user_permissions` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL,
  `permission_id` int(11) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `auth_user_user_permissions_user_id_permission_id_14a6b632_uniq` (`user_id`,`permission_id`),
  KEY `auth_user_user_permi_permission_id_1fbb5f2c_fk_auth_perm` (`permission_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `backup_job`
--

DROP TABLE IF EXISTS `backup_job`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `backup_job` (
  `job_id` int(11) NOT NULL AUTO_INCREMENT,
  `backup_type` varchar(20) NOT NULL,
  `backup_status` varchar(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `db_dump_path` varchar(500) DEFAULT NULL,
  `media_archive_path` varchar(500) DEFAULT NULL,
  `metadata_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL,
  `system_archive_path` varchar(500) DEFAULT NULL,
  PRIMARY KEY (`job_id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `budget_line`
--

DROP TABLE IF EXISTS `budget_line`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `budget_line` (
  `budget_line_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `fiscal_year` int(11) NOT NULL,
  `category` varchar(50) NOT NULL,
  `amount` decimal(12,2) NOT NULL,
  `notes` varchar(255) DEFAULT NULL,
  `updated_at` datetime(6) NOT NULL,
  PRIMARY KEY (`budget_line_id_PK`),
  UNIQUE KEY `uniq_budget_year_category` (`fiscal_year`,`category`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `bylaws_files`
--

DROP TABLE IF EXISTS `bylaws_files`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `bylaws_files` (
  `bylaws_file_id` int(11) NOT NULL AUTO_INCREMENT,
  `file_name` varchar(255) NOT NULL,
  `file_type` varchar(100) NOT NULL,
  `file_data` longblob NOT NULL,
  `file_size` int(11) NOT NULL,
  `file_hash` varchar(255) NOT NULL,
  `verification_status` varchar(50) NOT NULL,
  `uploaded_at` datetime(6) NOT NULL,
  `uploaded_by_user_id_FK` int(11) NOT NULL,
  `document_type` varchar(50) NOT NULL,
  `is_public_visible` tinyint(1) NOT NULL,
  PRIMARY KEY (`bylaws_file_id`),
  KEY `bylaws_files_uploaded_by_user_id__a1f6690c_fk_OFFICER_U` (`uploaded_by_user_id_FK`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `category`
--

DROP TABLE IF EXISTS `category`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `category` (
  `category_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `role` varchar(50) NOT NULL,
  PRIMARY KEY (`category_id_PK`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `certificate`
--

DROP TABLE IF EXISTS `certificate`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `certificate` (
  `certificate_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `certificate_number` varchar(50) NOT NULL,
  `pdf_file` varchar(100) DEFAULT NULL,
  `email_status` varchar(20) NOT NULL,
  `email_sent_at` datetime(6) DEFAULT NULL,
  `email_error` longtext NOT NULL,
  `generated_at` datetime(6) NOT NULL,
  `downloaded_at` datetime(6) DEFAULT NULL,
  `member_id_FK` int(11) NOT NULL,
  `event_id_FK` int(11) NOT NULL,
  PRIMARY KEY (`certificate_id_PK`),
  UNIQUE KEY `certificate_number` (`certificate_number`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `certificate_settings`
--

DROP TABLE IF EXISTS `certificate_settings`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `certificate_settings` (
  `settings_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `president_name` varchar(255) NOT NULL,
  `president_position` varchar(255) NOT NULL,
  `president_signature` varchar(100) DEFAULT NULL,
  `secretary_name` varchar(255) NOT NULL,
  `secretary_position` varchar(255) NOT NULL,
  `secretary_signature` varchar(100) DEFAULT NULL,
  `faculty_regent_name` varchar(255) NOT NULL,
  `faculty_regent_position` varchar(255) NOT NULL,
  `faculty_regent_signature` varchar(100) DEFAULT NULL,
  `organization_logo` varchar(100) DEFAULT NULL,
  `header_text` varchar(255) NOT NULL,
  `footer_text` longtext NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  PRIMARY KEY (`settings_id_PK`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `claimant`
--

DROP TABLE IF EXISTS `claimant`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `claimant` (
  `claimant_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `full_name` varchar(255) NOT NULL,
  `contact_number` varchar(50) DEFAULT NULL,
  `relationship_to_member` varchar(100) NOT NULL,
  `authorization_status` varchar(50) NOT NULL,
  `member_id_FK` int(11) NOT NULL,
  `relationship_group` varchar(20) NOT NULL,
  PRIMARY KEY (`claimant_id_PK`),
  KEY `CLAIMANT_member_id_FK_348a8f79_fk_MEMBER_member_id_PK` (`member_id_FK`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `contribution`
--

DROP TABLE IF EXISTS `contribution`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `contribution` (
  `contribution_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `expected_amount` decimal(10,2) NOT NULL,
  `paid_amount` decimal(10,2) NOT NULL,
  `payment_date` date DEFAULT NULL,
  `status` varchar(20) NOT NULL,
  `is_manually_overridden` tinyint(1) NOT NULL,
  `notes` longtext NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `aid_tracking_post_id_FK` int(11) NOT NULL,
  `member_id_FK` int(11) NOT NULL,
  `updated_by_user_id_FK` int(11) DEFAULT NULL,
  PRIMARY KEY (`contribution_id_PK`),
  UNIQUE KEY `CONTRIBUTION_aid_tracking_post_id_FK_member_id_FK_0bdaee32_uniq` (`aid_tracking_post_id_FK`,`member_id_FK`),
  KEY `CONTRIBUTION_member_id_FK_ed361721_fk_MEMBER_member_id_PK` (`member_id_FK`),
  KEY `CONTRIBUTION_updated_by_user_id_F_158d64bf_fk_OFFICER_U` (`updated_by_user_id_FK`)
) ENGINE=InnoDB AUTO_INCREMENT=132 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `death_aid`
--

DROP TABLE IF EXISTS `death_aid`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `death_aid` (
  `death_aid_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `claim_date` date NOT NULL,
  `claim_type` varchar(50) NOT NULL,
  `deceased_name` varchar(255) NOT NULL,
  `relationship_to_member` varchar(100) NOT NULL,
  `benefit_amount` decimal(10,2) NOT NULL,
  `document_status` varchar(50) NOT NULL,
  `status` varchar(50) NOT NULL,
  `president_decision` varchar(50) DEFAULT NULL,
  `release_reference` varchar(100) DEFAULT NULL,
  `acknowledgement_reference` varchar(100) DEFAULT NULL,
  `claimant_id_FK` int(11) NOT NULL,
  `member_id_FK` int(11) NOT NULL,
  `auditor_verified_by_user_id_FK` int(11) DEFAULT NULL,
  `president_decided_by_user_id_FK` int(11) DEFAULT NULL,
  `released_by_user_id_FK` int(11) DEFAULT NULL,
  `treasurer_validated_by_user_id_FK` int(11) DEFAULT NULL,
  `bill_amount` decimal(10,2) DEFAULT NULL,
  `funeral_location` varchar(255) NOT NULL,
  `interment_date` date DEFAULT NULL,
  `relationship_group` varchar(20) NOT NULL,
  `disbursement_source` varchar(20) DEFAULT NULL,
  `date_of_death` date DEFAULT NULL,
  PRIMARY KEY (`death_aid_id_PK`),
  KEY `DEATH_AID_claimant_id_FK_f0b13e0c_fk_CLAIMANT_claimant_id_PK` (`claimant_id_FK`),
  KEY `DEATH_AID_member_id_FK_ba2eae1b_fk_MEMBER_member_id_PK` (`member_id_FK`),
  KEY `DEATH_AID_auditor_verified_by__80ca4f33_fk_OFFICER_U` (`auditor_verified_by_user_id_FK`),
  KEY `DEATH_AID_president_decided_by_bcc1b2ff_fk_OFFICER_U` (`president_decided_by_user_id_FK`),
  KEY `DEATH_AID_treasurer_validated__54e09fac_fk_OFFICER_U` (`treasurer_validated_by_user_id_FK`),
  KEY `DEATH_AID_released_by_user_id_FK_c16b5c5b` (`released_by_user_id_FK`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `department`
--

DROP TABLE IF EXISTS `department`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `department` (
  `department_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `code` varchar(50) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `head_officer_id_FK` int(11) DEFAULT NULL,
  PRIMARY KEY (`department_id_PK`),
  UNIQUE KEY `code` (`code`),
  KEY `DEPARTMENT_head_officer_id_FK_9ade364b_fk_OFFICER_U` (`head_officer_id_FK`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `django_admin_log`
--

DROP TABLE IF EXISTS `django_admin_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `django_admin_log` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `action_time` datetime(6) NOT NULL,
  `object_id` longtext DEFAULT NULL,
  `object_repr` varchar(200) NOT NULL,
  `action_flag` smallint(5) unsigned NOT NULL,
  `change_message` longtext NOT NULL,
  `content_type_id` int(11) DEFAULT NULL,
  `user_id` int(11) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `django_admin_log_content_type_id_c4bce8eb_fk_django_co` (`content_type_id`),
  KEY `django_admin_log_user_id_c564eba6_fk_auth_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `django_content_type`
--

DROP TABLE IF EXISTS `django_content_type`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `django_content_type` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `app_label` varchar(100) NOT NULL,
  `model` varchar(100) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `django_content_type_app_label_model_76bd3d3b_uniq` (`app_label`,`model`)
) ENGINE=InnoDB AUTO_INCREMENT=76 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `django_migrations`
--

DROP TABLE IF EXISTS `django_migrations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `django_migrations` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `app` varchar(255) NOT NULL,
  `name` varchar(255) NOT NULL,
  `applied` datetime(6) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=190 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `django_session`
--

DROP TABLE IF EXISTS `django_session`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `django_session` (
  `session_key` varchar(40) NOT NULL,
  `session_data` longtext NOT NULL,
  `expire_date` datetime(6) NOT NULL,
  PRIMARY KEY (`session_key`),
  KEY `django_session_expire_date_a5c62663` (`expire_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `document`
--

DROP TABLE IF EXISTS `document`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `document` (
  `document_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `title` varchar(255) NOT NULL,
  `description` longtext NOT NULL,
  `document_type` varchar(50) NOT NULL,
  `category` varchar(100) NOT NULL,
  `keywords` varchar(500) NOT NULL,
  `tags` varchar(500) NOT NULL,
  `file_path` varchar(500) NOT NULL,
  `file_name` varchar(255) NOT NULL,
  `file_size` bigint(20) DEFAULT NULL,
  `file_type` varchar(50) NOT NULL,
  `version` varchar(20) NOT NULL,
  `uploaded_at` datetime(6) NOT NULL,
  `retention_period` date DEFAULT NULL,
  `is_archived` tinyint(1) NOT NULL,
  `uploaded_by_user_id_FK` int(11) DEFAULT NULL,
  `is_public_visible` tinyint(1) NOT NULL,
  `content_sha256` varchar(80) DEFAULT NULL,
  PRIMARY KEY (`document_id_PK`),
  KEY `DOCUMENT_uploaded_by_user_id__2d5af3d8_fk_OFFICER_U` (`uploaded_by_user_id_FK`),
  KEY `document_content_sha256_2c228a49` (`content_sha256`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `document_activity`
--

DROP TABLE IF EXISTS `document_activity`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `document_activity` (
  `activity_id` int(11) NOT NULL AUTO_INCREMENT,
  `action` varchar(50) NOT NULL,
  `officer_name` varchar(255) NOT NULL,
  `details` longtext NOT NULL,
  `timestamp` datetime(6) NOT NULL,
  `document_id_FK` int(11) DEFAULT NULL,
  `officer_id_FK` int(11) DEFAULT NULL,
  PRIMARY KEY (`activity_id`),
  KEY `DOCUMENT_ACTIVITY_document_id_FK_2c1d21b5_fk_DOCUMENT_` (`document_id_FK`),
  KEY `DOCUMENT_ACTIVITY_officer_id_FK_e46a0d41_fk_OFFICER_U` (`officer_id_FK`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `document_pin`
--

DROP TABLE IF EXISTS `document_pin`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `document_pin` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `pinned_at` datetime(6) NOT NULL,
  `document_id_FK` int(11) NOT NULL,
  `officer_id_FK` int(11) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `DOCUMENT_PIN_document_id_FK_officer_id_FK_776da9b1_uniq` (`document_id_FK`,`officer_id_FK`),
  KEY `DOCUMENT_PIN_officer_id_FK_36d52f31_fk_OFFICER_USER_user_id_PK` (`officer_id_FK`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `event`
--

DROP TABLE IF EXISTS `event`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `event` (
  `event_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `title` varchar(255) NOT NULL,
  `description` longtext NOT NULL,
  `venue` varchar(255) NOT NULL,
  `event_date` date NOT NULL,
  `event_time` time(6) NOT NULL,
  `end_time` time(6) DEFAULT NULL,
  `event_type` varchar(100) NOT NULL,
  `status` varchar(20) NOT NULL,
  `attendance_open` tinyint(1) NOT NULL,
  `attendance_closed` tinyint(1) NOT NULL,
  `quorum_required` int(11) NOT NULL,
  `quorum_reached` tinyint(1) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `created_by_user_id_FK` int(11) DEFAULT NULL,
  `auto_generate_certificates` tinyint(1) NOT NULL,
  `certificate_issue_date` date DEFAULT NULL,
  `certificate_prefix` varchar(20) NOT NULL,
  `given_place` varchar(255) NOT NULL,
  PRIMARY KEY (`event_id_PK`),
  KEY `EVENT_created_by_user_id_FK_ace80cb6_fk_OFFICER_USER_user_id_PK` (`created_by_user_id_FK`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `event_type`
--

DROP TABLE IF EXISTS `event_type`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `event_type` (
  `event_type_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`event_type_id_PK`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `feedback_answer`
--

DROP TABLE IF EXISTS `feedback_answer`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `feedback_answer` (
  `answer_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `value_text` longtext NOT NULL,
  `value_int` int(11) DEFAULT NULL,
  `value_list` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`value_list`)),
  `question_id_FK` int(11) NOT NULL,
  `response_id_FK` int(11) NOT NULL,
  PRIMARY KEY (`answer_id_PK`),
  KEY `feedback_answer_question_id_FK_8b07a409_fk_feedback_` (`question_id_FK`),
  KEY `feedback_answer_response_id_FK_8fe05784_fk_feedback_` (`response_id_FK`),
  CONSTRAINT `feedback_answer_question_id_FK_8b07a409_fk_feedback_` FOREIGN KEY (`question_id_FK`) REFERENCES `feedback_question` (`question_id_PK`),
  CONSTRAINT `feedback_answer_response_id_FK_8fe05784_fk_feedback_` FOREIGN KEY (`response_id_FK`) REFERENCES `feedback_response` (`response_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=17 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `feedback_form`
--

DROP TABLE IF EXISTS `feedback_form`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `feedback_form` (
  `form_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `title` varchar(200) NOT NULL,
  `section_title` varchar(200) NOT NULL,
  `description` longtext NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `is_open` tinyint(1) NOT NULL,
  `is_archived` tinyint(1) NOT NULL,
  `show_on_roles` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`show_on_roles`)),
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `created_by_id_FK` int(11) DEFAULT NULL,
  `kind` varchar(10) NOT NULL,
  `paired_pre_FK` int(11) DEFAULT NULL,
  PRIMARY KEY (`form_id_PK`),
  KEY `feedback_form_created_by_id_FK_90e98662_fk_officer_u` (`created_by_id_FK`),
  KEY `feedback_form_paired_pre_FK_acfe6596_fk_feedback_form_form_id_PK` (`paired_pre_FK`),
  CONSTRAINT `feedback_form_created_by_id_FK_90e98662_fk_officer_u` FOREIGN KEY (`created_by_id_FK`) REFERENCES `officer_user` (`user_id_PK`),
  CONSTRAINT `feedback_form_paired_pre_FK_acfe6596_fk_feedback_form_form_id_PK` FOREIGN KEY (`paired_pre_FK`) REFERENCES `feedback_form` (`form_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `feedback_question`
--

DROP TABLE IF EXISTS `feedback_question`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `feedback_question` (
  `question_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `prompt` varchar(400) NOT NULL,
  `qtype` varchar(10) NOT NULL,
  `options` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`options`)),
  `scale_min` smallint(5) unsigned NOT NULL CHECK (`scale_min` >= 0),
  `scale_max` smallint(5) unsigned NOT NULL CHECK (`scale_max` >= 0),
  `min_choices` smallint(5) unsigned NOT NULL CHECK (`min_choices` >= 0),
  `max_choices` smallint(5) unsigned NOT NULL CHECK (`max_choices` >= 0),
  `is_required` tinyint(1) NOT NULL,
  `display_order` int(10) unsigned NOT NULL CHECK (`display_order` >= 0),
  `help_text` varchar(300) NOT NULL,
  `form_id_FK` int(11) NOT NULL,
  PRIMARY KEY (`question_id_PK`),
  KEY `feedback_question_form_id_FK_96e949bf_fk_feedback_` (`form_id_FK`),
  CONSTRAINT `feedback_question_form_id_FK_96e949bf_fk_feedback_` FOREIGN KEY (`form_id_FK`) REFERENCES `feedback_form` (`form_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `feedback_response`
--

DROP TABLE IF EXISTS `feedback_response`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `feedback_response` (
  `response_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `submitted_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `ip_address` char(39) DEFAULT NULL,
  `device_info` varchar(255) NOT NULL,
  `form_id_FK` int(11) NOT NULL,
  `officer_id_FK` int(11) NOT NULL,
  PRIMARY KEY (`response_id_PK`),
  UNIQUE KEY `uniq_feedback_response_per_officer` (`form_id_FK`,`officer_id_FK`),
  KEY `feedback_response_officer_id_FK_a67b8d32_fk_officer_u` (`officer_id_FK`),
  CONSTRAINT `feedback_response_form_id_FK_cd2fa7f3_fk_feedback_` FOREIGN KEY (`form_id_FK`) REFERENCES `feedback_form` (`form_id_PK`),
  CONSTRAINT `feedback_response_officer_id_FK_a67b8d32_fk_officer_u` FOREIGN KEY (`officer_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `financial_document_archive`
--

DROP TABLE IF EXISTS `financial_document_archive`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `financial_document_archive` (
  `document_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `related_module` varchar(100) NOT NULL,
  `related_record_id` int(11) NOT NULL,
  `document_type` varchar(100) NOT NULL,
  `file_path` varchar(500) NOT NULL,
  `file_hash` varchar(255) NOT NULL,
  `verification_status` varchar(50) NOT NULL,
  `uploaded_at` datetime(6) NOT NULL,
  `uploaded_by_user_id_FK` int(11) NOT NULL,
  `file_name` varchar(255) NOT NULL,
  `file_type` varchar(100) NOT NULL,
  PRIMARY KEY (`document_id_PK`),
  KEY `FINANCIAL_DOCUMENT_A_uploaded_by_user_id__2e803a5e_fk_OFFICER_U` (`uploaded_by_user_id_FK`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `fund_transaction`
--

DROP TABLE IF EXISTS `fund_transaction`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `fund_transaction` (
  `transaction_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `direction` varchar(10) NOT NULL,
  `amount` decimal(12,2) NOT NULL,
  `source_type` varchar(50) NOT NULL,
  `source_id` int(11) NOT NULL,
  `description` varchar(255) NOT NULL,
  `reference_number` varchar(100) DEFAULT NULL,
  `recorded_at` datetime(6) NOT NULL,
  `recorded_by_user_id_FK` int(11) NOT NULL,
  PRIMARY KEY (`transaction_id_PK`),
  KEY `FUND_TRANSACTION_recorded_by_user_id__4d5f9ffd_fk_OFFICER_U` (`recorded_by_user_id_FK`),
  KEY `fund_transa_directi_6f3d56_idx` (`direction`),
  KEY `fund_transa_source__dbfb67_idx` (`source_type`,`source_id`),
  KEY `fund_transa_recorde_cc8f2c_idx` (`recorded_at` DESC)
) ENGINE=InnoDB AUTO_INCREMENT=1573 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `global_audit_trail`
--

DROP TABLE IF EXISTS `global_audit_trail`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `global_audit_trail` (
  `trail_id` int(11) NOT NULL AUTO_INCREMENT,
  `table_name` varchar(100) NOT NULL,
  `record_id` int(11) NOT NULL,
  `action` varchar(50) NOT NULL,
  `old_values` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL,
  `new_values` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL,
  `actor_type` varchar(50) NOT NULL,
  `actor_id` int(11) DEFAULT NULL,
  `actor_name` varchar(255) NOT NULL,
  `ip_address` char(39) DEFAULT NULL,
  `device_info` varchar(255) DEFAULT NULL,
  `notes` longtext DEFAULT NULL,
  `timestamp` datetime(6) NOT NULL,
  `document_archive_id_FK` int(11) DEFAULT NULL,
  `entry_hash` varchar(64) NOT NULL,
  `hmac_signature` varchar(64) NOT NULL,
  `previous_hash` varchar(64) NOT NULL,
  `result` varchar(20) NOT NULL,
  PRIMARY KEY (`trail_id`),
  KEY `global_audi_table_n_2b627d_idx` (`table_name`,`record_id`,`timestamp`),
  KEY `GLOBAL_AUDIT_TRAIL_document_archive_id__cd699f95_fk_FINANCIAL` (`document_archive_id_FK`),
  KEY `global_audit_trail_timestamp_88225144` (`timestamp`)
) ENGINE=InnoDB AUTO_INCREMENT=4137 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `hero_slide`
--

DROP TABLE IF EXISTS `hero_slide`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `hero_slide` (
  `hero_id` int(11) NOT NULL AUTO_INCREMENT,
  `title` varchar(255) NOT NULL,
  `subtitle` longtext NOT NULL,
  `image` varchar(100) DEFAULT NULL,
  `button_text` varchar(50) NOT NULL,
  `button_url` varchar(500) NOT NULL,
  `sort_order` int(11) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  PRIMARY KEY (`hero_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `login_attempt_log`
--

DROP TABLE IF EXISTS `login_attempt_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `login_attempt_log` (
  `attempt_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `username_used` varchar(150) NOT NULL,
  `ip_address` char(39) NOT NULL,
  `device_info` varchar(255) DEFAULT NULL,
  `result` varchar(50) NOT NULL,
  `attempted_at` datetime(6) NOT NULL,
  `user_id_FK` int(11) DEFAULT NULL,
  PRIMARY KEY (`attempt_id_PK`),
  KEY `LOGIN_ATTEMPT_LOG_user_id_FK_3d7e6e0a_fk_OFFICER_USER_user_id_PK` (`user_id_FK`)
) ENGINE=InnoDB AUTO_INCREMENT=223 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `medical_aid`
--

DROP TABLE IF EXISTS `medical_aid`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `medical_aid` (
  `medical_aid_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `request_date` date NOT NULL,
  `hospital_bill_amount` decimal(10,2) NOT NULL,
  `claim_year` int(11) NOT NULL,
  `document_status` varchar(50) NOT NULL,
  `policy_record_status` varchar(50) NOT NULL,
  `validated_aid_amount` decimal(10,2) NOT NULL,
  `status` varchar(50) NOT NULL,
  `president_decision` varchar(50) DEFAULT NULL,
  `release_reference` varchar(100) DEFAULT NULL,
  `acknowledgement_reference` varchar(100) DEFAULT NULL,
  `member_id_FK` int(11) NOT NULL,
  `auditor_verified_by_user_id_FK` int(11) DEFAULT NULL,
  `president_decided_by_user_id_FK` int(11) DEFAULT NULL,
  `released_by_user_id_FK` int(11) DEFAULT NULL,
  `treasurer_validated_by_user_id_FK` int(11) DEFAULT NULL,
  `requested_amount` decimal(10,2) DEFAULT NULL,
  `hospital_name` varchar(255) NOT NULL,
  `hospital_date` varchar(50) DEFAULT NULL,
  `disbursement_source` varchar(20) DEFAULT NULL,
  `admission_date` date DEFAULT NULL,
  `discharge_date` date DEFAULT NULL,
  `hospital_address` varchar(500) DEFAULT NULL,
  `reason_for_request` longtext DEFAULT NULL,
  PRIMARY KEY (`medical_aid_id_PK`),
  KEY `MEDICAL_AID_member_id_FK_a3f6c869_fk_MEMBER_member_id_PK` (`member_id_FK`),
  KEY `MEDICAL_AID_auditor_verified_by__d16afda1_fk_OFFICER_U` (`auditor_verified_by_user_id_FK`),
  KEY `MEDICAL_AID_president_decided_by_8781c5c8_fk_OFFICER_U` (`president_decided_by_user_id_FK`),
  KEY `MEDICAL_AID_treasurer_validated__621f73b2_fk_OFFICER_U` (`treasurer_validated_by_user_id_FK`),
  KEY `MEDICAL_AID_released_by_user_id_FK_77cb71e1` (`released_by_user_id_FK`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `member`
--

DROP TABLE IF EXISTS `member`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `member` (
  `member_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `full_name` varchar(255) NOT NULL,
  `contact_number` varchar(255) DEFAULT NULL,
  `email` varchar(255) DEFAULT NULL,
  `employment_status` varchar(50) NOT NULL,
  `membership_status` varchar(50) NOT NULL,
  `member_type` varchar(50) NOT NULL,
  `date_joined` date NOT NULL,
  `department` varchar(100) DEFAULT NULL,
  `employee_id` varchar(50) DEFAULT NULL,
  `position` varchar(100) DEFAULT NULL,
  `department_id_FK` int(11) DEFAULT NULL,
  `officer_user_id_FK` int(11) DEFAULT NULL,
  `profile_picture` varchar(100) DEFAULT NULL,
  `pin_code` varchar(255) DEFAULT NULL,
  `qr_code` varchar(100) DEFAULT NULL,
  `emergency_contact` varchar(255) DEFAULT NULL,
  `emergency_number` varchar(255) DEFAULT NULL,
  `setup_complete` tinyint(1) NOT NULL,
  `qr_data` varchar(255) DEFAULT NULL,
  `dashboard_access` varchar(20) NOT NULL,
  `push_notifications` tinyint(1) NOT NULL DEFAULT 1,
  `member_classification` varchar(20) NOT NULL,
  `push_enabled` tinyint(1) NOT NULL,
  `address` longtext DEFAULT NULL,
  `civil_status` varchar(20) DEFAULT NULL,
  `date_of_birth` date DEFAULT NULL,
  `sex` varchar(10) DEFAULT NULL,
  `dues_backfill_pending` tinyint(1) NOT NULL,
  PRIMARY KEY (`member_id_PK`),
  UNIQUE KEY `MEMBER_employee_id_6c5f9503_uniq` (`employee_id`),
  KEY `MEMBER_department_id_FK_4098768a_fk_DEPARTMENT_department_id_PK` (`department_id_FK`),
  KEY `MEMBER_officer_user_id_FK_884d61d4_fk_OFFICER_USER_user_id_PK` (`officer_user_id_FK`)
) ENGINE=InnoDB AUTO_INCREMENT=132 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `member_assessment_allocations`
--

DROP TABLE IF EXISTS `member_assessment_allocations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `member_assessment_allocations` (
  `allocation_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `amount_applied` decimal(10,2) NOT NULL,
  `amount_remaining` decimal(10,2) NOT NULL,
  `assessment_item_id_FK` int(11) NOT NULL,
  `member_assessment_id_FK` int(11) NOT NULL,
  PRIMARY KEY (`allocation_id_PK`),
  UNIQUE KEY `member_assessment_alloca_member_assessment_id_FK__1ea437cd_uniq` (`member_assessment_id_FK`,`assessment_item_id_FK`),
  KEY `member_assessment_al_assessment_item_id_F_bdfb196d_fk_assessmen` (`assessment_item_id_FK`),
  CONSTRAINT `member_assessment_al_assessment_item_id_F_bdfb196d_fk_assessmen` FOREIGN KEY (`assessment_item_id_FK`) REFERENCES `assessment_items` (`item_id_PK`),
  CONSTRAINT `member_assessment_al_member_assessment_id_e2e64467_fk_member_as` FOREIGN KEY (`member_assessment_id_FK`) REFERENCES `member_assessments` (`member_assessment_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=1583 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `member_assessments`
--

DROP TABLE IF EXISTS `member_assessments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `member_assessments` (
  `member_assessment_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `standard_assessment` decimal(10,2) NOT NULL,
  `actual_deduction` decimal(10,2) NOT NULL,
  `outstanding_balance` decimal(10,2) NOT NULL,
  `status` varchar(50) NOT NULL,
  `recorded_at` datetime(6) NOT NULL,
  `verified_at` datetime(6) DEFAULT NULL,
  `approved_at` datetime(6) DEFAULT NULL,
  `approved_by_id_FK` int(11) DEFAULT NULL,
  `member_id_FK` int(11) NOT NULL,
  `recorded_by_id_FK` int(11) DEFAULT NULL,
  `verified_by_id_FK` int(11) DEFAULT NULL,
  `assessment_id_FK` int(11) NOT NULL,
  `prior_month` varchar(50) DEFAULT NULL,
  `prior_outstanding` decimal(10,2) NOT NULL,
  `prior_outstanding_collected` decimal(10,2) NOT NULL,
  `change_amount` decimal(10,2) NOT NULL,
  `is_excluded` tinyint(1) NOT NULL,
  `prior_collected_months` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`prior_collected_months`)),
  `prior_months` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`prior_months`)),
  PRIMARY KEY (`member_assessment_id_PK`),
  UNIQUE KEY `member_assessments_assessment_id_FK_member_id_FK_4d898dd9_uniq` (`assessment_id_FK`,`member_id_FK`),
  KEY `member_assessments_approved_by_id_FK_382b64f0_fk_officer_u` (`approved_by_id_FK`),
  KEY `member_assessments_recorded_by_id_FK_35692580_fk_officer_u` (`recorded_by_id_FK`),
  KEY `member_assessments_verified_by_id_FK_2079d1c0_fk_officer_u` (`verified_by_id_FK`),
  KEY `member_asse_member__711e24_idx` (`member_id_FK`,`status`,`assessment_id_FK`),
  CONSTRAINT `member_assessments_approved_by_id_FK_382b64f0_fk_officer_u` FOREIGN KEY (`approved_by_id_FK`) REFERENCES `officer_user` (`user_id_PK`),
  CONSTRAINT `member_assessments_assessment_id_FK_8d921b9b_fk_monthly_a` FOREIGN KEY (`assessment_id_FK`) REFERENCES `monthly_assessments` (`assessment_id_PK`),
  CONSTRAINT `member_assessments_member_id_FK_8c9c953f_fk_member_member_id_PK` FOREIGN KEY (`member_id_FK`) REFERENCES `member` (`member_id_PK`),
  CONSTRAINT `member_assessments_recorded_by_id_FK_35692580_fk_officer_u` FOREIGN KEY (`recorded_by_id_FK`) REFERENCES `officer_user` (`user_id_PK`),
  CONSTRAINT `member_assessments_verified_by_id_FK_2079d1c0_fk_officer_u` FOREIGN KEY (`verified_by_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=1149 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `member_catchup_dues`
--

DROP TABLE IF EXISTS `member_catchup_dues`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `member_catchup_dues` (
  `catchup_due_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `month` date NOT NULL,
  `amount` decimal(10,2) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `created_by_id_FK` int(11) DEFAULT NULL,
  `member_id_FK` int(11) NOT NULL,
  PRIMARY KEY (`catchup_due_id_PK`),
  UNIQUE KEY `member_catchup_dues_member_id_FK_month_b9dc9d80_uniq` (`member_id_FK`,`month`),
  KEY `member_catc_member__b6ea3f_idx` (`member_id_FK`,`month`),
  KEY `member_catchup_dues_created_by_id_FK_16060c8b_fk_officer_u` (`created_by_id_FK`),
  CONSTRAINT `member_catchup_dues_created_by_id_FK_16060c8b_fk_officer_u` FOREIGN KEY (`created_by_id_FK`) REFERENCES `officer_user` (`user_id_PK`),
  CONSTRAINT `member_catchup_dues_member_id_FK_08220ceb_fk_member_member_id_PK` FOREIGN KEY (`member_id_FK`) REFERENCES `member` (`member_id_PK`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `member_ledger`
--

DROP TABLE IF EXISTS `member_ledger`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `member_ledger` (
  `ledger_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `transaction_type` varchar(50) NOT NULL,
  `amount` decimal(12,2) NOT NULL,
  `direction` varchar(10) NOT NULL,
  `balance_after` decimal(12,2) NOT NULL,
  `reference_id` int(11) DEFAULT NULL,
  `reference_type` varchar(50) DEFAULT NULL,
  `description` varchar(255) DEFAULT NULL,
  `notes` longtext DEFAULT NULL,
  `recorded_at` datetime(6) NOT NULL,
  `member_id_FK` int(11) NOT NULL,
  `recorded_by_user_id_FK` int(11) NOT NULL,
  PRIMARY KEY (`ledger_id_PK`),
  KEY `MEMBER_LEDGER_recorded_by_user_id__ea4dfc59_fk_OFFICER_U` (`recorded_by_user_id_FK`),
  KEY `member_ledg_member__159877_idx` (`member_id_FK`),
  KEY `member_ledg_transac_f0013b_idx` (`transaction_type`),
  KEY `member_ledg_recorde_aeb626_idx` (`recorded_at`),
  KEY `member_ledg_member__f9c06a_idx` (`member_id_FK`,`recorded_at`,`ledger_id_PK`),
  KEY `member_ledg_referen_0d5b44_idx` (`reference_type`,`reference_id`)
) ENGINE=InnoDB AUTO_INCREMENT=1047 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `member_registration_request`
--

DROP TABLE IF EXISTS `member_registration_request`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `member_registration_request` (
  `request_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `full_name` varchar(255) NOT NULL,
  `employee_id` varchar(50) NOT NULL,
  `email` varchar(255) DEFAULT NULL,
  `department` varchar(100) DEFAULT NULL,
  `position` varchar(100) DEFAULT NULL,
  `membership_category` varchar(50) NOT NULL,
  `payment_method` varchar(50) NOT NULL,
  `amount` decimal(10,2) NOT NULL,
  `receipt_number` varchar(100) NOT NULL,
  `reference_number` varchar(100) DEFAULT NULL,
  `payment_date` date DEFAULT NULL,
  `status` varchar(50) NOT NULL,
  `returned_reason` longtext DEFAULT NULL,
  `submitted_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `submitted_by_ip` char(39) DEFAULT NULL,
  `submitted_by_user_agent` varchar(255) DEFAULT NULL,
  `processed_by_user_id_FK` int(11) DEFAULT NULL,
  `password_hash` varchar(255) DEFAULT NULL,
  `auditor_verified_by_user_id_FK` int(11) DEFAULT NULL,
  `president_approved_by_user_id_FK` int(11) DEFAULT NULL,
  `treasurer_verified_by_user_id_FK` int(11) DEFAULT NULL,
  `account_creation_requested` tinyint(1) NOT NULL,
  `contact_number` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`request_id_PK`),
  KEY `MEMBER_REGISTRATION__auditor_verified_by__fd89364e_fk_OFFICER_U` (`auditor_verified_by_user_id_FK`),
  KEY `MEMBER_REGISTRATION__president_approved_b_8619f09f_fk_OFFICER_U` (`president_approved_by_user_id_FK`),
  KEY `MEMBER_REGISTRATION__treasurer_verified_b_a88205c4_fk_OFFICER_U` (`treasurer_verified_by_user_id_FK`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `membership_fee`
--

DROP TABLE IF EXISTS `membership_fee`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `membership_fee` (
  `fee_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `amount` decimal(10,2) NOT NULL,
  `payment_date` date NOT NULL,
  `payment_status` varchar(50) NOT NULL,
  `receipt_number` varchar(100) DEFAULT NULL,
  `deposit_reference` varchar(100) DEFAULT NULL,
  `member_id_FK` int(11) NOT NULL,
  `recorded_by_user_id_FK` int(11) NOT NULL,
  `payment_method` varchar(50) NOT NULL,
  PRIMARY KEY (`fee_id_PK`),
  UNIQUE KEY `MEMBERSHIP_FEE_member_id_FK_receipt_number_fa8cb308_uniq` (`member_id_FK`,`receipt_number`),
  KEY `MEMBERSHIP_FEE_recorded_by_user_id__e50e2c50_fk_OFFICER_U` (`recorded_by_user_id_FK`)
) ENGINE=InnoDB AUTO_INCREMENT=132 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `mfa_backup_code`
--

DROP TABLE IF EXISTS `mfa_backup_code`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `mfa_backup_code` (
  `code_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `code_hash` varchar(128) NOT NULL,
  `used_at` datetime(6) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  `officer_id_FK` int(11) NOT NULL,
  PRIMARY KEY (`code_id_PK`),
  KEY `mfa_backup_code_officer_id_FK_ac883e06_fk_officer_u` (`officer_id_FK`),
  CONSTRAINT `mfa_backup_code_officer_id_FK_ac883e06_fk_officer_u` FOREIGN KEY (`officer_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=31 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `minutes`
--

DROP TABLE IF EXISTS `minutes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `minutes` (
  `minutes_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `meeting_title` varchar(255) NOT NULL,
  `meeting_date` date NOT NULL,
  `venue` varchar(255) NOT NULL,
  `attendees` longtext NOT NULL,
  `agenda` longtext NOT NULL,
  `minutes_content` longtext NOT NULL,
  `status` varchar(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `prepared_by_user_id_FK` int(11) DEFAULT NULL,
  `event_id_FK` int(11) DEFAULT NULL,
  `document_id_FK` int(11) DEFAULT NULL,
  PRIMARY KEY (`minutes_id_PK`),
  KEY `MINUTES_prepared_by_user_id__f10e2bf9_fk_OFFICER_U` (`prepared_by_user_id_FK`),
  KEY `MINUTES_event_id_FK_352800da_fk_EVENT_event_id_PK` (`event_id_FK`),
  KEY `MINUTES_document_id_FK_3dab1eff_fk_DOCUMENT_document_id_PK` (`document_id_FK`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `monthly_assessment_documents`
--

DROP TABLE IF EXISTS `monthly_assessment_documents`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `monthly_assessment_documents` (
  `document_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `kind` varchar(30) NOT NULL,
  `image` varchar(500) NOT NULL,
  `uploaded_at` datetime(6) NOT NULL,
  `assessment_id_FK` int(11) NOT NULL,
  `uploaded_by_id_FK` int(11) DEFAULT NULL,
  `content_sha256` varchar(64) DEFAULT NULL,
  `norm_sha256` varchar(64) DEFAULT NULL,
  PRIMARY KEY (`document_id_PK`),
  KEY `monthly_assessment_d_assessment_id_FK_ad9f4255_fk_monthly_a` (`assessment_id_FK`),
  KEY `monthly_assessment_d_uploaded_by_id_FK_f33c2001_fk_officer_u` (`uploaded_by_id_FK`),
  KEY `monthly_assessment_documents_content_sha256_64b1d2ad` (`content_sha256`),
  KEY `monthly_assessment_documents_norm_sha256_ac761804` (`norm_sha256`),
  CONSTRAINT `monthly_assessment_d_assessment_id_FK_ad9f4255_fk_monthly_a` FOREIGN KEY (`assessment_id_FK`) REFERENCES `monthly_assessments` (`assessment_id_PK`),
  CONSTRAINT `monthly_assessment_d_uploaded_by_id_FK_f33c2001_fk_officer_u` FOREIGN KEY (`uploaded_by_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=27 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `monthly_assessments`
--

DROP TABLE IF EXISTS `monthly_assessments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `monthly_assessments` (
  `assessment_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `month` date NOT NULL,
  `total_amount` decimal(10,2) NOT NULL,
  `status` varchar(50) NOT NULL,
  `treasurer_remarks` longtext DEFAULT NULL,
  `auditor_remarks` longtext DEFAULT NULL,
  `president_remarks` longtext DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `created_by_id_FK` int(11) DEFAULT NULL,
  `deposit_reference` varchar(100) DEFAULT NULL,
  `deposited_amount` decimal(10,2) DEFAULT NULL,
  `deposited_at` datetime(6) DEFAULT NULL,
  `deposited_by_id_FK` int(11) DEFAULT NULL,
  PRIMARY KEY (`assessment_id_PK`),
  UNIQUE KEY `month` (`month`),
  KEY `monthly_assessments_created_by_id_FK_6576a030_fk_officer_u` (`created_by_id_FK`),
  KEY `monthly_ass_status_390138_idx` (`status`,`month`),
  KEY `monthly_assessments_deposited_by_id_FK_5cc1fae1_fk_officer_u` (`deposited_by_id_FK`),
  CONSTRAINT `monthly_assessments_created_by_id_FK_6576a030_fk_officer_u` FOREIGN KEY (`created_by_id_FK`) REFERENCES `officer_user` (`user_id_PK`),
  CONSTRAINT `monthly_assessments_deposited_by_id_FK_5cc1fae1_fk_officer_u` FOREIGN KEY (`deposited_by_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=17 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `monthly_dues`
--

DROP TABLE IF EXISTS `monthly_dues`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `monthly_dues` (
  `dues_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `month_covered` varchar(50) NOT NULL,
  `amount` decimal(10,2) NOT NULL,
  `payment_method` varchar(50) NOT NULL,
  `payment_status` varchar(50) NOT NULL,
  `receipt_number` varchar(100) DEFAULT NULL,
  `deduction_batch_reference` varchar(100) DEFAULT NULL,
  `remittance_reference` varchar(100) DEFAULT NULL,
  `member_id_FK` int(11) NOT NULL,
  `recorded_by_user_id_FK` int(11) NOT NULL,
  `payment_date` date DEFAULT NULL,
  `treasurer_status` varchar(50) NOT NULL,
  `treasurer_id_FK` int(11) DEFAULT NULL,
  `treasurer_remarks` longtext DEFAULT NULL,
  `treasurer_approved_at` datetime(6) DEFAULT NULL,
  `auditor_status` varchar(50) NOT NULL,
  `auditor_id_FK` int(11) DEFAULT NULL,
  `auditor_remarks` longtext DEFAULT NULL,
  `auditor_approved_at` datetime(6) DEFAULT NULL,
  `president_status` varchar(50) NOT NULL,
  `president_id_FK` int(11) DEFAULT NULL,
  `president_remarks` longtext DEFAULT NULL,
  `president_approved_at` datetime(6) DEFAULT NULL,
  `is_advance` tinyint(1) NOT NULL,
  PRIMARY KEY (`dues_id_PK`),
  KEY `MONTHLY_DUES_member_id_FK_70adcf99_fk_MEMBER_member_id_PK` (`member_id_FK`),
  KEY `MONTHLY_DUES_recorded_by_user_id__a84ebfb3_fk_OFFICER_U` (`recorded_by_user_id_FK`),
  KEY `MONTHLY_DUES_treasurer_id_FK_2ce5f468_fk_OFFICER_USER_user_id_PK` (`treasurer_id_FK`),
  KEY `MONTHLY_DUES_auditor_id_FK_fd49c27d_fk_OFFICER_USER_user_id_PK` (`auditor_id_FK`),
  KEY `MONTHLY_DUES_president_id_FK_08476f2c_fk_OFFICER_USER_user_id_PK` (`president_id_FK`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `news_article`
--

DROP TABLE IF EXISTS `news_article`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `news_article` (
  `news_id` int(11) NOT NULL AUTO_INCREMENT,
  `title` varchar(255) NOT NULL,
  `slug` varchar(255) NOT NULL,
  `summary` longtext NOT NULL,
  `content` longtext NOT NULL,
  `featured_image` varchar(100) DEFAULT NULL,
  `event_date` date DEFAULT NULL,
  `event_time` time(6) DEFAULT NULL,
  `venue` varchar(255) NOT NULL,
  `video_url` varchar(200) NOT NULL,
  `video_thumbnail` varchar(100) DEFAULT NULL,
  `is_featured` tinyint(1) NOT NULL,
  `is_published` tinyint(1) NOT NULL,
  `published_at` datetime(6) DEFAULT NULL,
  `view_count` int(11) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `author_id` int(11) DEFAULT NULL,
  `category_id` int(11) DEFAULT NULL,
  PRIMARY KEY (`news_id`),
  UNIQUE KEY `slug` (`slug`),
  KEY `NEWS_ARTICLE_author_id_04dc2507_fk_OFFICER_USER_user_id_PK` (`author_id`),
  KEY `NEWS_ARTICLE_category_id_630b7031_fk_NEWS_CATEGORY_category_id` (`category_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `news_category`
--

DROP TABLE IF EXISTS `news_category`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `news_category` (
  `category_id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `slug` varchar(100) NOT NULL,
  `description` longtext NOT NULL,
  `icon` varchar(50) NOT NULL,
  `order` int(11) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  PRIMARY KEY (`category_id`),
  UNIQUE KEY `name` (`name`),
  UNIQUE KEY `slug` (`slug`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `news_gallery`
--

DROP TABLE IF EXISTS `news_gallery`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `news_gallery` (
  `gallery_id` int(11) NOT NULL AUTO_INCREMENT,
  `caption` varchar(255) NOT NULL,
  `image` varchar(100) NOT NULL,
  `is_featured` tinyint(1) NOT NULL,
  `order` int(11) NOT NULL,
  `uploaded_at` datetime(6) NOT NULL,
  `article_id` int(11) NOT NULL,
  PRIMARY KEY (`gallery_id`),
  KEY `NEWS_GALLERY_article_id_3ad83410_fk_NEWS_ARTICLE_news_id` (`article_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `notification`
--

DROP TABLE IF EXISTS `notification`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `notification` (
  `notification_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `recipient_type` varchar(50) NOT NULL,
  `recipient_id` int(11) NOT NULL,
  `recipient_name` varchar(255) NOT NULL,
  `recipient_contact` varchar(255) DEFAULT NULL,
  `notification_type` varchar(50) NOT NULL,
  `message` longtext NOT NULL,
  `delivery_status` varchar(50) NOT NULL,
  `sent_at` datetime(6) NOT NULL,
  `category` varchar(20) DEFAULT NULL,
  `channel` varchar(20) DEFAULT NULL,
  `error_message` longtext DEFAULT NULL,
  `overdue_bucket` varchar(10) DEFAULT NULL,
  `related_post_id_FK` int(11) DEFAULT NULL,
  `scheduled_date` datetime(6) DEFAULT NULL,
  `is_read` tinyint(1) NOT NULL,
  `receipt_number` varchar(255) DEFAULT NULL,
  `sender_name` varchar(255) DEFAULT NULL,
  `sender_role` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`notification_id_PK`),
  KEY `NOTIFICATION_related_post_id_FK_e61541a2_fk_AID_TRACK` (`related_post_id_FK`),
  KEY `notificatio_recipie_9e152a_idx` (`recipient_type`,`recipient_id`,`sent_at`,`notification_id_PK`),
  KEY `notificatio_recipie_e611ec_idx` (`recipient_type`,`recipient_id`,`is_read`)
) ENGINE=InnoDB AUTO_INCREMENT=1573 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `officer_profile`
--

DROP TABLE IF EXISTS `officer_profile`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `officer_profile` (
  `officer_profile_id` int(11) NOT NULL AUTO_INCREMENT,
  `full_name` varchar(255) NOT NULL,
  `position` varchar(100) NOT NULL,
  `category` varchar(50) NOT NULL,
  `department` varchar(255) DEFAULT NULL,
  `school_year` varchar(50) DEFAULT NULL,
  `term_start` date DEFAULT NULL,
  `term_end` date DEFAULT NULL,
  `email` varchar(255) DEFAULT NULL,
  `facebook` varchar(200) DEFAULT NULL,
  `biography` longtext DEFAULT NULL,
  `photo` varchar(100) DEFAULT NULL,
  `status` varchar(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `created_by_id` int(11) DEFAULT NULL,
  PRIMARY KEY (`officer_profile_id`),
  KEY `OFFICER_PROFILE_created_by_id_d435d405_fk_OFFICER_U` (`created_by_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `officer_user`
--

DROP TABLE IF EXISTS `officer_user`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `officer_user` (
  `user_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `full_name` varchar(255) NOT NULL,
  `username` varchar(150) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `role` varchar(50) NOT NULL,
  `account_status` varchar(50) NOT NULL,
  `term_start` date DEFAULT NULL,
  `term_end` date DEFAULT NULL,
  `mfa_secret` varchar(500) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `mfa_enabled` tinyint(1) NOT NULL,
  `last_mfa_email_sent_at` datetime(6) DEFAULT NULL,
  `department_id_FK` int(11) DEFAULT NULL,
  `email` varchar(255) DEFAULT NULL,
  `must_change_password` tinyint(1) NOT NULL,
  `authenticator_enabled` tinyint(1) NOT NULL,
  `authenticator_enrolled_at` datetime(6) DEFAULT NULL,
  `authenticator_secret` varchar(500) DEFAULT NULL,
  `backup_codes_issued_at` datetime(6) DEFAULT NULL,
  `action_pin_hash` varchar(255) DEFAULT NULL,
  `action_pin_set_at` datetime(6) DEFAULT NULL,
  `action_pin_fail_count` int(11) NOT NULL,
  `action_pin_locked_until` datetime(6) DEFAULT NULL,
  `action_pin_lock_minutes` int(11) NOT NULL,
  PRIMARY KEY (`user_id_PK`),
  UNIQUE KEY `username` (`username`),
  KEY `OFFICER_USER_department_id_FK_cc12815d_fk_DEPARTMEN` (`department_id_FK`)
) ENGINE=InnoDB AUTO_INCREMENT=385 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `offline_bot_challenge`
--

DROP TABLE IF EXISTS `offline_bot_challenge`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `offline_bot_challenge` (
  `challenge_id` varchar(64) NOT NULL,
  `username` varchar(150) NOT NULL,
  `salt` varchar(64) NOT NULL,
  `difficulty` int(11) NOT NULL,
  `expires_at` datetime(6) NOT NULL,
  `used_at` datetime(6) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`challenge_id`),
  KEY `obc_user_exp_idx` (`username`,`expires_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `organization_fund_report`
--

DROP TABLE IF EXISTS `organization_fund_report`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `organization_fund_report` (
  `report_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `report_period` varchar(20) NOT NULL,
  `report_type` varchar(20) NOT NULL,
  `report_status` varchar(50) NOT NULL,
  `file_path` varchar(500) NOT NULL,
  `approved_at` datetime(6) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `approved_by_user_id_FK` int(11) DEFAULT NULL,
  `prepared_by_user_id_FK` int(11) NOT NULL,
  `auditor_verified_at` datetime(6) DEFAULT NULL,
  `auditor_verified_by_user_id_FK` int(11) DEFAULT NULL,
  `return_reason` longtext NOT NULL,
  `report_filters` varchar(300) NOT NULL,
  `report_rows` longtext NOT NULL,
  `report_title` varchar(200) NOT NULL,
  PRIMARY KEY (`report_id_PK`),
  KEY `ORGANIZATION_FUND_RE_approved_by_user_id__a8823df8_fk_OFFICER_U` (`approved_by_user_id_FK`),
  KEY `ORGANIZATION_FUND_RE_prepared_by_user_id__f419a1e5_fk_OFFICER_U` (`prepared_by_user_id_FK`),
  KEY `ORGANIZATION_FUND_RE_auditor_verified_by__2a461a6a_fk_OFFICER_U` (`auditor_verified_by_user_id_FK`),
  CONSTRAINT `ORGANIZATION_FUND_RE_auditor_verified_by__2a461a6a_fk_OFFICER_U` FOREIGN KEY (`auditor_verified_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `outgoing_email`
--

DROP TABLE IF EXISTS `outgoing_email`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `outgoing_email` (
  `outgoing_email_id` int(11) NOT NULL AUTO_INCREMENT,
  `recipient_list` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `subject` varchar(255) NOT NULL,
  `html_template` varchar(255) NOT NULL,
  `context` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `status` varchar(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `sent_at` datetime(6) DEFAULT NULL,
  `error_message` longtext NOT NULL,
  `retry_count` int(11) NOT NULL,
  `claimed_at` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`outgoing_email_id`)
) ENGINE=InnoDB AUTO_INCREMENT=1512 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `payroll_batch`
--

DROP TABLE IF EXISTS `payroll_batch`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `payroll_batch` (
  `batch_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `payroll_period` varchar(7) NOT NULL,
  `total_amount` decimal(12,2) NOT NULL,
  `member_count` int(11) NOT NULL,
  `notes` longtext NOT NULL,
  `hardcopy_reference` varchar(100) DEFAULT NULL,
  `status` varchar(50) NOT NULL,
  `auditor_verified_at` datetime(6) DEFAULT NULL,
  `auditor_remarks` longtext DEFAULT NULL,
  `returned_reason` longtext DEFAULT NULL,
  `president_approved_at` datetime(6) DEFAULT NULL,
  `president_remarks` longtext DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `archive_id_FK` int(11) DEFAULT NULL,
  `auditor_verified_by_user_id_FK` int(11) DEFAULT NULL,
  `president_approved_by_user_id_FK` int(11) DEFAULT NULL,
  `recorded_by_user_id_FK` int(11) NOT NULL,
  `returned_by_user_id_FK` int(11) DEFAULT NULL,
  PRIMARY KEY (`batch_id_PK`),
  KEY `PAYROLL_BATCH_archive_id_FK_c8cd48a0_fk_transacti` (`archive_id_FK`),
  KEY `PAYROLL_BATCH_auditor_verified_by__1214d668_fk_OFFICER_U` (`auditor_verified_by_user_id_FK`),
  KEY `PAYROLL_BATCH_president_approved_b_d7cb885f_fk_OFFICER_U` (`president_approved_by_user_id_FK`),
  KEY `PAYROLL_BATCH_recorded_by_user_id__f63b35cb_fk_OFFICER_U` (`recorded_by_user_id_FK`),
  KEY `PAYROLL_BATCH_returned_by_user_id__25fe28ed_fk_OFFICER_U` (`returned_by_user_id_FK`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `payroll_deduction`
--

DROP TABLE IF EXISTS `payroll_deduction`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `payroll_deduction` (
  `deduction_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `amount` decimal(10,2) NOT NULL,
  `category` varchar(50) NOT NULL,
  `fund_impact` varchar(10) NOT NULL,
  `month_covered` varchar(7) DEFAULT NULL,
  `notes` longtext NOT NULL,
  `aid_tracking_post_id_FK` int(11) DEFAULT NULL,
  `batch_id_FK` int(11) NOT NULL,
  `member_id_FK` int(11) NOT NULL,
  PRIMARY KEY (`deduction_id_PK`),
  KEY `PAYROLL_DEDUCTION_aid_tracking_post_id_14171c63_fk_AID_TRACK` (`aid_tracking_post_id_FK`),
  KEY `payroll_ded_batch_i_cd4980_idx` (`batch_id_FK`,`category`),
  KEY `payroll_ded_member__faf0a3_idx` (`member_id_FK`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `photo`
--

DROP TABLE IF EXISTS `photo`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `photo` (
  `photo_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `image` varchar(100) NOT NULL,
  `caption` varchar(255) NOT NULL,
  `is_featured` tinyint(1) NOT NULL,
  `uploaded_at` datetime(6) NOT NULL,
  `album_id` int(11) NOT NULL,
  `uploaded_by_id` int(11) DEFAULT NULL,
  PRIMARY KEY (`photo_id_PK`),
  KEY `PHOTO_album_id_ad2092d5_fk_ALBUM_album_id_PK` (`album_id`),
  KEY `PHOTO_uploaded_by_id_ba7c3a3a_fk_OFFICER_USER_user_id_PK` (`uploaded_by_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `position_category`
--

DROP TABLE IF EXISTS `position_category`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `position_category` (
  `category_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `created_by_user_id_FK` int(11) DEFAULT NULL,
  PRIMARY KEY (`category_id_PK`),
  UNIQUE KEY `name` (`name`),
  KEY `position_category_created_by_user_id_F_66c04755_fk_officer_u` (`created_by_user_id_FK`),
  CONSTRAINT `position_category_created_by_user_id_F_66c04755_fk_officer_u` FOREIGN KEY (`created_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=13 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `position_rank`
--

DROP TABLE IF EXISTS `position_rank`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `position_rank` (
  `position_rank_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `category` varchar(100) NOT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT 1,
  `created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  `created_by_user_id_FK` int(11) DEFAULT NULL,
  PRIMARY KEY (`position_rank_id_PK`),
  UNIQUE KEY `name` (`name`),
  KEY `fk_position_rank_officer` (`created_by_user_id_FK`),
  CONSTRAINT `fk_position_rank_officer` FOREIGN KEY (`created_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=23 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `push_subscription`
--

DROP TABLE IF EXISTS `push_subscription`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `push_subscription` (
  `subscription_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `officer_id_FK` int(11) DEFAULT NULL,
  `endpoint` varchar(500) NOT NULL,
  `p256dh_key` varchar(256) NOT NULL,
  `auth_key` varchar(128) NOT NULL,
  `user_agent` varchar(500) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `member_id_FK` int(11) DEFAULT NULL,
  `origin` varchar(500) DEFAULT NULL,
  PRIMARY KEY (`subscription_id_PK`),
  UNIQUE KEY `PUSH_SUBSCRIPTION_officer_id_FK_endpoint_d8da377b_uniq` (`officer_id_FK`,`endpoint`),
  UNIQUE KEY `PUSH_SUBSCRIPTION_member_id_FK_endpoint_3df284e5_uniq` (`member_id_FK`,`endpoint`),
  CONSTRAINT `PUSH_SUBSCRIPTION_member_id_FK_b189b200_fk_MEMBER_member_id_PK` FOREIGN KEY (`member_id_FK`) REFERENCES `member` (`member_id_PK`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `revision_log`
--

DROP TABLE IF EXISTS `revision_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `revision_log` (
  `log_id` int(11) NOT NULL AUTO_INCREMENT,
  `object_id` int(10) unsigned NOT NULL,
  `rejection_reason` longtext NOT NULL,
  `snapshot_data` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `auditor_id_FK` int(11) DEFAULT NULL,
  `content_type_id` int(11) NOT NULL,
  PRIMARY KEY (`log_id`),
  KEY `revision_log_auditor_id_FK_86a7849b_fk_OFFICER_USER_user_id_PK` (`auditor_id_FK`),
  KEY `revision_lo_content_6da5e6_idx` (`content_type_id`,`object_id`),
  KEY `revision_lo_created_91651d_idx` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `salary_deduction_exemption`
--

DROP TABLE IF EXISTS `salary_deduction_exemption`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `salary_deduction_exemption` (
  `exemption_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `month_covered` varchar(50) NOT NULL,
  `reason` longtext DEFAULT NULL,
  `status` varchar(50) NOT NULL,
  `requested_at` datetime(6) NOT NULL,
  `requested_by_member` tinyint(1) NOT NULL,
  `reviewed_at` datetime(6) DEFAULT NULL,
  `review_remarks` longtext DEFAULT NULL,
  `member_id_FK` int(11) NOT NULL,
  `reviewed_by_user_id_FK` int(11) DEFAULT NULL,
  PRIMARY KEY (`exemption_id_PK`),
  UNIQUE KEY `salary_deduction_exempti_member_id_FK_month_cover_uniq` (`member_id_FK`,`month_covered`),
  KEY `salary_deduction_exe_reviewed_by_fk_officer` (`reviewed_by_user_id_FK`),
  CONSTRAINT `salary_deduction_exe_member_id_FK_fk_member` FOREIGN KEY (`member_id_FK`) REFERENCES `member` (`member_id_PK`),
  CONSTRAINT `salary_deduction_exe_reviewed_by_fk_officer` FOREIGN KEY (`reviewed_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `sensitive_read_log`
--

DROP TABLE IF EXISTS `sensitive_read_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `sensitive_read_log` (
  `read_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `module` varchar(100) NOT NULL,
  `record_id` int(11) NOT NULL,
  `purpose` varchar(255) NOT NULL,
  `timestamp` datetime(6) NOT NULL,
  `user_id_FK` int(11) NOT NULL,
  `device_info` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`read_id_PK`),
  KEY `SENSITIVE_READ_LOG_user_id_FK_f41bb5ec_fk_OFFICER_U` (`user_id_FK`)
) ENGINE=InnoDB AUTO_INCREMENT=23622 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `supporting_proof`
--

DROP TABLE IF EXISTS `supporting_proof`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `supporting_proof` (
  `proof_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `object_id` int(10) unsigned NOT NULL,
  `file_path` varchar(500) NOT NULL,
  `file_name` varchar(255) NOT NULL,
  `file_type` varchar(100) NOT NULL,
  `file_sha256` varchar(64) NOT NULL,
  `row_signature` varchar(64) NOT NULL,
  `uploaded_at` datetime(6) NOT NULL,
  `content_type_id` int(11) NOT NULL,
  `uploaded_by_user_id_FK` int(11) DEFAULT NULL,
  `document_type` varchar(50) NOT NULL,
  PRIMARY KEY (`proof_id_PK`),
  KEY `SUPPORTING_PROOF_uploaded_by_user_id__a400d09d_fk_OFFICER_U` (`uploaded_by_user_id_FK`),
  KEY `SUPPORTING__content_09c351_idx` (`content_type_id`,`object_id`),
  KEY `SUPPORTING__uploade_b01f8c_idx` (`uploaded_at`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `system_setting`
--

DROP TABLE IF EXISTS `system_setting`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `system_setting` (
  `setting_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `setting_key` varchar(100) NOT NULL,
  `setting_value` longtext NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `updated_by_id_FK` int(11) DEFAULT NULL,
  PRIMARY KEY (`setting_id_PK`),
  UNIQUE KEY `setting_key` (`setting_key`),
  KEY `SYSTEM_SETTING_updated_by_id_FK_d79d01db_fk_OFFICER_U` (`updated_by_id_FK`)
) ENGINE=InnoDB AUTO_INCREMENT=49 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `transaction_archive`
--

DROP TABLE IF EXISTS `transaction_archive`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `transaction_archive` (
  `archive_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `transaction_type` varchar(50) NOT NULL,
  `record_id` int(11) NOT NULL,
  `member_name` varchar(255) NOT NULL,
  `amount` decimal(10,2) NOT NULL,
  `validated_amount` decimal(10,2) DEFAULT NULL,
  `status` varchar(50) NOT NULL,
  `payment_method` varchar(50) DEFAULT NULL,
  `release_reference` varchar(100) DEFAULT NULL,
  `verified_at` datetime(6) DEFAULT NULL,
  `archived_at` datetime(6) NOT NULL,
  `archived_by_user_id_FK` int(11) DEFAULT NULL,
  `member_id_FK` int(11) DEFAULT NULL,
  `released_by_user_id_FK` int(11) DEFAULT NULL,
  `fiscal_term` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`archive_id_PK`),
  KEY `transaction_archive_archived_by_user_id__95d87e41_fk_OFFICER_U` (`archived_by_user_id_FK`),
  KEY `transaction_archive_member_id_FK_166fdd68_fk_MEMBER_member_id_PK` (`member_id_FK`),
  KEY `transaction_archive_released_by_user_id__7db2dcd2_fk_OFFICER_U` (`released_by_user_id_FK`),
  KEY `transaction_transac_4a6ac9_idx` (`transaction_type`,`record_id`),
  KEY `transaction_status_abeab9_idx` (`status`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `transaction_verification`
--

DROP TABLE IF EXISTS `transaction_verification`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `transaction_verification` (
  `verification_id` int(11) NOT NULL AUTO_INCREMENT,
  `table_name` varchar(50) NOT NULL,
  `record_id` int(11) NOT NULL,
  `verification_status` varchar(50) NOT NULL,
  `verified_at` datetime(6) DEFAULT NULL,
  `approved_at` datetime(6) DEFAULT NULL,
  `auditor_id_FK` int(11) DEFAULT NULL,
  `president_id_FK` int(11) DEFAULT NULL,
  `auditor_remarks` longtext DEFAULT NULL,
  `evidence_file_hash` varchar(255) DEFAULT NULL,
  `evidence_file_path` varchar(500) DEFAULT NULL,
  `return_count` int(11) NOT NULL,
  `returned_by_auditor_id_FK` int(11) DEFAULT NULL,
  `returned_reason` longtext DEFAULT NULL,
  `target_category` varchar(50) DEFAULT NULL,
  `deposit_slip_reference` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`verification_id`),
  KEY `transaction_verifica_auditor_id_FK_36530d09_fk_OFFICER_U` (`auditor_id_FK`),
  KEY `transaction_verifica_president_id_FK_3c6de749_fk_OFFICER_U` (`president_id_FK`),
  KEY `transaction_verifica_returned_by_auditor__690b24a6_fk_OFFICER_U` (`returned_by_auditor_id_FK`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `workflow_logs`
--

DROP TABLE IF EXISTS `workflow_logs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `workflow_logs` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `action` varchar(50) NOT NULL,
  `notes` longtext DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  `performed_by_id_FK` int(11) DEFAULT NULL,
  `assessment_id_FK` int(11) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `workflow_logs_performed_by_id_FK_594d3e7d_fk_officer_u` (`performed_by_id_FK`),
  KEY `workflow_logs_assessment_id_FK_98a85f39_fk_monthly_a` (`assessment_id_FK`),
  CONSTRAINT `workflow_logs_assessment_id_FK_98a85f39_fk_monthly_a` FOREIGN KEY (`assessment_id_FK`) REFERENCES `monthly_assessments` (`assessment_id_PK`),
  CONSTRAINT `workflow_logs_performed_by_id_FK_594d3e7d_fk_officer_u` FOREIGN KEY (`performed_by_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=155 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping events for database 'isucaufafms_capstone_project_db'
--

--
-- Dumping routines for database 'isucaufafms_capstone_project_db'
--
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*M!100616 SET NOTE_VERBOSITY=@OLD_NOTE_VERBOSITY */;

-- Dump completed on 2026-10-16  7:59:15
