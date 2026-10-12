/*
SQLyog Ultimate v13.1.1 (64 bit)
MySQL - 12.0.2-MariaDB : Database - capstone_project_db
*********************************************************************
*/

/*!40101 SET NAMES utf8 */;

/*!40101 SET SQL_MODE=''*/;

/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;
CREATE DATABASE /*!32312 IF NOT EXISTS*/`capstone_project_db` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci */;

USE `capstone_project_db`;

/*Table structure for table `access_session` */

DROP TABLE IF EXISTS `access_session`;

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
  `last_verified_location` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`last_verified_location`)),
  `session_policy` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`session_policy`)),
  `trusted_device` tinyint(1) NOT NULL,
  PRIMARY KEY (`session_id_PK`),
  UNIQUE KEY `token_id` (`token_id`),
  KEY `ACCESS_SESSION_user_id_FK_525a0de2_fk_OFFICER_USER_user_id_PK` (`user_id_FK`),
  CONSTRAINT `ACCESS_SESSION_user_id_FK_525a0de2_fk_OFFICER_USER_user_id_PK` FOREIGN KEY (`user_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=74 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `access_session` */

insert  into `access_session`(`session_id_PK`,`token_id`,`ip_address`,`device_info`,`issued_at`,`expires_at`,`revoked_at`,`session_status`,`user_id_FK`,`last_verified_location`,`session_policy`,`trusted_device`) values 
(55,'rE1qwtyT14qpiaJ3sQXJ3zCVkmrGq4tuw3kU5wmzRqo','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','2026-07-27 11:46:18.448529','2026-07-27 19:46:18.443163',NULL,'Active',40,NULL,'{}',0),
(56,'BmQY_AR3uaKYuE8FvLaP_4gHOwzDUV7-84oIFqbrVYU','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','2026-07-27 11:46:35.735690','2026-07-27 19:46:35.735690',NULL,'Active',41,'{\"ip\": \"127.0.0.1\"}','{\"zt_verified_at\": \"2026-07-27T12:03:49.177556+00:00\"}',1),
(57,'92ItNxbkbvXoBpi_aPzZzRd8HykKaUulXEL6yR4DQLA','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','2026-07-27 11:51:34.105209','2026-07-27 19:51:34.103359',NULL,'Active',42,NULL,'{}',0),
(58,'5tPkhkmRyrsoEq64M-XTnGIKJhAb0ia2jElKgbs8FTs','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','2026-07-27 11:52:30.094342','2026-07-27 19:52:30.094342',NULL,'Active',43,'{\"ip\": \"127.0.0.1\"}','{\"zt_verified_at\": \"2026-07-27T12:03:07.199591+00:00\"}',1),
(59,'-MBfJlpytL99KHPJVmXEKAeCqJ4wjgg4IBH8q0K2gCs','192.168.1.4','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','2026-07-27 11:54:54.169617','2026-07-27 19:54:54.169107','2026-07-27 12:00:31.462526','Revoked',45,NULL,'{}',0),
(60,'eJKdU1C1f8vCr4dCuoJHK-Fo3gf0H2HW9GTb6xNhYSM','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','2026-07-27 11:59:37.771170','2026-07-27 19:59:37.769602',NULL,'Active',44,NULL,'{}',0),
(61,'Bbyf0Ph1Wt6R3dc4XwYjI4mD00DTCFQtL0WaAV-fraA','192.168.1.4','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','2026-07-27 12:04:29.105135','2026-07-27 20:04:29.105135',NULL,'Active',46,NULL,'{}',0),
(62,'yXwRdlEJoWsIy60ZYi8slBxylqmMrNJemmHlX050QeM','192.168.1.4','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','2026-07-27 12:36:44.535918','2026-07-27 20:36:44.535918',NULL,'Active',45,NULL,'{}',0),
(63,'e0ouTxtbKNhtl6flU-GBsH0e051USM9ppxVtuHYte-Q','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','2026-07-28 08:07:20.036927','2026-07-28 16:07:20.035459','2026-07-28 12:52:07.449074','Revoked',44,NULL,'{}',0),
(64,'lq-eB4ZStUtaN4rtawTaRd9hDGj2kPwzs3cMFwRSYu8','127.0.0.1','Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','2026-07-28 08:07:53.425911','2026-07-28 16:07:53.425911',NULL,'Active',45,NULL,'{}',0),
(65,'npFlYbHTTuyyRd6f-5FrKa1joV2U3HR-pRr8YBY_5Yk','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','2026-07-28 09:09:23.485099','2026-07-28 17:09:23.485099',NULL,'Active',44,NULL,'{}',0),
(66,'Vgc6ew0R_nhpHjtVzQo-9wsCd8oCSLFNqZjGdY8tEUY','127.0.0.1','Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1','2026-07-28 09:11:26.567865','2026-07-28 17:11:26.567865',NULL,'Active',45,NULL,'{}',0),
(67,'QORD6RfwG4MarGus3In0yIQuvY3dv3W5WF5iDRSakHY','192.168.1.4','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','2026-07-28 09:29:22.012365','2026-07-28 17:29:22.012365',NULL,'Active',45,NULL,'{}',0),
(68,'Lhk2zC9qtU8oK30yfjCIDtRnTyNROQVScC6BOdekM-A','127.0.0.1','Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1','2026-07-28 12:52:24.816102','2026-07-28 20:52:24.816102',NULL,'Active',45,NULL,'{}',0),
(69,'526bPwIRqpykDkWm19wXHrUfxbpPfZuU8MKr1OnH040','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','2026-07-28 22:24:52.934439','2026-07-29 06:24:52.913850',NULL,'Active',44,NULL,'{}',0),
(70,'ORBT6dH6r98tH6_2JnyMYsW0yRW4pyRyIdrXJIs4m28','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','2026-07-28 22:24:53.724335','2026-07-29 06:24:53.723323',NULL,'Active',44,NULL,'{}',0),
(71,'oa1PqOSppJoKVf_wMFSEadOb3gxN4Bqry3y3eqCSETY','192.168.1.4','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','2026-07-28 22:26:51.859606','2026-07-29 06:26:51.854599',NULL,'Active',45,NULL,'{}',0),
(72,'PMZQnRlxFo7z6vcJoYsqQodndDYzaBLw4Ex2SQF0wUY','127.0.0.1','Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1','2026-07-29 10:05:08.885371','2026-07-29 18:05:08.884361',NULL,'Active',45,NULL,'{}',0),
(73,'xXCJaKYpJBOuGsRb1Z5Kv4KiAISfPb5KC8whIsuZ71Q','192.168.1.4','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','2026-07-29 10:44:09.998661','2026-07-29 18:44:09.996653',NULL,'Active',45,NULL,'{}',0);

/*Table structure for table `aid_tracking_post` */

DROP TABLE IF EXISTS `aid_tracking_post`;

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
  PRIMARY KEY (`post_id_PK`),
  KEY `AID_TRACKING_POST_archive_id_FK_2bff15c8_fk_transacti` (`archive_id_FK`),
  KEY `AID_TRACKING_POST_created_by_user_id_F_a3a13677_fk_OFFICER_U` (`created_by_user_id_FK`),
  CONSTRAINT `AID_TRACKING_POST_archive_id_FK_2bff15c8_fk_transacti` FOREIGN KEY (`archive_id_FK`) REFERENCES `transaction_archive` (`archive_id_PK`),
  CONSTRAINT `AID_TRACKING_POST_created_by_user_id_F_a3a13677_fk_OFFICER_U` FOREIGN KEY (`created_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `aid_tracking_post` */

/*Table structure for table `announcement` */

DROP TABLE IF EXISTS `announcement`;

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
  PRIMARY KEY (`announcement_id_PK`),
  KEY `ANNOUNCEMENT_published_by_user_id_1867ecbe_fk_OFFICER_U` (`published_by_user_id_FK`),
  CONSTRAINT `ANNOUNCEMENT_published_by_user_id_1867ecbe_fk_OFFICER_U` FOREIGN KEY (`published_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `announcement` */

/*Table structure for table `attendance` */

DROP TABLE IF EXISTS `attendance`;

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
  KEY `ATTENDANCE_event_id_FK_1fe0a37c_fk_EVENT_event_id_PK` (`event_id_FK`),
  CONSTRAINT `ATTENDANCE_event_id_FK_1fe0a37c_fk_EVENT_event_id_PK` FOREIGN KEY (`event_id_FK`) REFERENCES `event` (`event_id_PK`),
  CONSTRAINT `ATTENDANCE_member_id_FK_977d6132_fk_MEMBER_member_id_PK` FOREIGN KEY (`member_id_FK`) REFERENCES `member` (`member_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=27 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `attendance` */

insert  into `attendance`(`attendance_id_PK`,`date`,`check_in_time`,`check_out_time`,`status`,`check_in_method`,`member_id_FK`,`event_id_FK`) values 
(1,'2026-07-27','20:19:40.182891',NULL,'Late','QR',13,NULL),
(2,'2026-07-27','20:26:30.239857',NULL,'Late','QR',14,NULL),
(3,'2026-07-28','17:30:01.975439',NULL,'Late','QR',13,3),
(4,'2026-07-28','17:30:27.313363',NULL,'Late','QR',14,3),
(5,'2026-07-28','18:27:17.344188',NULL,'Present','PIN',14,4),
(6,'2026-07-28','18:28:03.717931',NULL,'Present','QR',13,4),
(7,'2026-07-28','18:32:33.632998',NULL,'Present','QR',14,5),
(8,'2026-07-28','18:33:10.651087',NULL,'Present','QR',13,5),
(9,'2026-07-28','18:35:19.066301',NULL,'Present','QR',13,6),
(10,'2026-07-28','18:40:02.705974',NULL,'Present','QR',13,7),
(11,'2026-07-28','18:56:07.970946',NULL,'Present','QR',13,8),
(12,'2026-07-28','19:20:24.991497',NULL,'Present','QR',13,9),
(13,'2026-07-28','19:33:08.478111',NULL,'Present','PIN',14,10),
(14,'2026-07-28','19:33:12.734910',NULL,'Present','PIN',13,10),
(15,'2026-07-28','19:34:20.357271',NULL,'Present','PIN',14,11),
(16,'2026-07-28','19:34:25.759474',NULL,'Present','PIN',13,11),
(17,'2026-07-28','20:01:58.692631',NULL,'Present','QR',13,12),
(18,'2026-07-28','21:38:44.603159',NULL,'Present','PIN',14,13),
(19,'2026-07-28','21:38:50.260475',NULL,'Present','PIN',13,13),
(20,'2026-07-28','21:45:19.959030',NULL,'Present','PIN',14,14),
(21,'2026-07-28','21:48:37.158116',NULL,'Present','PIN',14,15),
(22,'2026-07-28','21:48:45.773386',NULL,'Present','PIN',13,15),
(23,'2026-07-28','22:02:11.415214',NULL,'Present','PIN',14,16),
(24,'2026-07-28','22:13:58.123286',NULL,'Late','PIN',13,16),
(25,'2026-07-28','22:15:13.882333',NULL,'Present','PIN',14,17),
(26,'2026-07-28','22:15:24.221491',NULL,'Present','PIN',13,17);

/*Table structure for table `audit_findings_report` */

DROP TABLE IF EXISTS `audit_findings_report`;

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
  KEY `AUDIT_FINDINGS_REPOR_prepared_by_user_id__537aa0f1_fk_OFFICER_U` (`prepared_by_user_id_FK`),
  CONSTRAINT `AUDIT_FINDINGS_REPOR_certified_by_user_id_d3493449_fk_OFFICER_U` FOREIGN KEY (`certified_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`),
  CONSTRAINT `AUDIT_FINDINGS_REPOR_prepared_by_user_id__537aa0f1_fk_OFFICER_U` FOREIGN KEY (`prepared_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `audit_findings_report` */

/*Table structure for table `auth_group` */

DROP TABLE IF EXISTS `auth_group`;

CREATE TABLE `auth_group` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(150) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `auth_group` */

/*Table structure for table `auth_group_permissions` */

DROP TABLE IF EXISTS `auth_group_permissions`;

CREATE TABLE `auth_group_permissions` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `group_id` int(11) NOT NULL,
  `permission_id` int(11) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `auth_group_permissions_group_id_permission_id_0cd325b0_uniq` (`group_id`,`permission_id`),
  KEY `auth_group_permissio_permission_id_84c5c92e_fk_auth_perm` (`permission_id`),
  CONSTRAINT `auth_group_permissio_permission_id_84c5c92e_fk_auth_perm` FOREIGN KEY (`permission_id`) REFERENCES `auth_permission` (`id`),
  CONSTRAINT `auth_group_permissions_group_id_b120cbf9_fk_auth_group_id` FOREIGN KEY (`group_id`) REFERENCES `auth_group` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `auth_group_permissions` */

/*Table structure for table `auth_permission` */

DROP TABLE IF EXISTS `auth_permission`;

CREATE TABLE `auth_permission` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `content_type_id` int(11) NOT NULL,
  `codename` varchar(100) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `auth_permission_content_type_id_codename_01ab375a_uniq` (`content_type_id`,`codename`),
  CONSTRAINT `auth_permission_content_type_id_2f476e4b_fk_django_co` FOREIGN KEY (`content_type_id`) REFERENCES `django_content_type` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=193 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `auth_permission` */

insert  into `auth_permission`(`id`,`name`,`content_type_id`,`codename`) values 
(1,'Can add log entry',6,'add_logentry'),
(2,'Can change log entry',6,'change_logentry'),
(3,'Can delete log entry',6,'delete_logentry'),
(4,'Can view log entry',6,'view_logentry'),
(5,'Can add user',7,'add_user'),
(6,'Can change user',7,'change_user'),
(7,'Can delete user',7,'delete_user'),
(8,'Can view user',7,'view_user'),
(9,'Can add group',8,'add_group'),
(10,'Can change group',8,'change_group'),
(11,'Can delete group',8,'delete_group'),
(12,'Can view group',8,'view_group'),
(13,'Can add permission',9,'add_permission'),
(14,'Can change permission',9,'change_permission'),
(15,'Can delete permission',9,'delete_permission'),
(16,'Can view permission',9,'view_permission'),
(17,'Can add content type',10,'add_contenttype'),
(18,'Can change content type',10,'change_contenttype'),
(19,'Can delete content type',10,'delete_contenttype'),
(20,'Can view content type',10,'view_contenttype'),
(21,'Can add session',11,'add_session'),
(22,'Can change session',11,'change_session'),
(23,'Can delete session',11,'delete_session'),
(24,'Can view session',11,'view_session'),
(25,'Can add sensitive read log',12,'add_sensitivereadlog'),
(26,'Can change sensitive read log',12,'change_sensitivereadlog'),
(27,'Can delete sensitive read log',12,'delete_sensitivereadlog'),
(28,'Can view sensitive read log',12,'view_sensitivereadlog'),
(29,'Can add outgoing email',13,'add_outgoingemail'),
(30,'Can change outgoing email',13,'change_outgoingemail'),
(31,'Can delete outgoing email',13,'delete_outgoingemail'),
(32,'Can view outgoing email',13,'view_outgoingemail'),
(33,'Can add backup job',14,'add_backupjob'),
(34,'Can change backup job',14,'change_backupjob'),
(35,'Can delete backup job',14,'delete_backupjob'),
(36,'Can view backup job',14,'view_backupjob'),
(37,'Can add payroll deduction',15,'add_payrolldeduction'),
(38,'Can change payroll deduction',15,'change_payrolldeduction'),
(39,'Can delete payroll deduction',15,'delete_payrolldeduction'),
(40,'Can view payroll deduction',15,'view_payrolldeduction'),
(41,'Can add bylaws file',16,'add_bylawsfile'),
(42,'Can change bylaws file',16,'change_bylawsfile'),
(43,'Can delete bylaws file',16,'delete_bylawsfile'),
(44,'Can view bylaws file',16,'view_bylawsfile'),
(45,'Can add global audit trail',17,'add_globalaudittrail'),
(46,'Can change global audit trail',17,'change_globalaudittrail'),
(47,'Can delete global audit trail',17,'delete_globalaudittrail'),
(48,'Can view global audit trail',17,'view_globalaudittrail'),
(49,'Can add monthly dues',5,'add_monthlydues'),
(50,'Can change monthly dues',5,'change_monthlydues'),
(51,'Can delete monthly dues',5,'delete_monthlydues'),
(52,'Can view monthly dues',5,'view_monthlydues'),
(53,'Can add payroll batch',18,'add_payrollbatch'),
(54,'Can change payroll batch',18,'change_payrollbatch'),
(55,'Can delete payroll batch',18,'delete_payrollbatch'),
(56,'Can view payroll batch',18,'view_payrollbatch'),
(57,'Can add medical aid',2,'add_medicalaid'),
(58,'Can change medical aid',2,'change_medicalaid'),
(59,'Can delete medical aid',2,'delete_medicalaid'),
(60,'Can view medical aid',2,'view_medicalaid'),
(61,'Can add claimant',19,'add_claimant'),
(62,'Can change claimant',19,'change_claimant'),
(63,'Can delete claimant',19,'delete_claimant'),
(64,'Can view claimant',19,'view_claimant'),
(65,'Can add department',20,'add_department'),
(66,'Can change department',20,'change_department'),
(67,'Can delete department',20,'delete_department'),
(68,'Can view department',20,'view_department'),
(69,'Can add audit findings report',21,'add_auditfindingsreport'),
(70,'Can change audit findings report',21,'change_auditfindingsreport'),
(71,'Can delete audit findings report',21,'delete_auditfindingsreport'),
(72,'Can view audit findings report',21,'view_auditfindingsreport'),
(73,'Can add supporting proof',22,'add_supportingproof'),
(74,'Can change supporting proof',22,'change_supportingproof'),
(75,'Can delete supporting proof',22,'delete_supportingproof'),
(76,'Can view supporting proof',22,'view_supportingproof'),
(77,'Can add login attempt log',23,'add_loginattemptlog'),
(78,'Can change login attempt log',23,'change_loginattemptlog'),
(79,'Can delete login attempt log',23,'delete_loginattemptlog'),
(80,'Can view login attempt log',23,'view_loginattemptlog'),
(81,'Can add notification',24,'add_notification'),
(82,'Can change notification',24,'change_notification'),
(83,'Can delete notification',24,'delete_notification'),
(84,'Can view notification',24,'view_notification'),
(85,'Can add system setting',25,'add_systemsetting'),
(86,'Can change system setting',25,'change_systemsetting'),
(87,'Can delete system setting',25,'delete_systemsetting'),
(88,'Can view system setting',25,'view_systemsetting'),
(89,'Can add member',26,'add_member'),
(90,'Can change member',26,'change_member'),
(91,'Can delete member',26,'delete_member'),
(92,'Can view member',26,'view_member'),
(93,'Can add financial document archive',27,'add_financialdocumentarchive'),
(94,'Can change financial document archive',27,'change_financialdocumentarchive'),
(95,'Can delete financial document archive',27,'delete_financialdocumentarchive'),
(96,'Can view financial document archive',27,'view_financialdocumentarchive'),
(97,'Can add aid tracking post',28,'add_aidtrackingpost'),
(98,'Can change aid tracking post',28,'change_aidtrackingpost'),
(99,'Can delete aid tracking post',28,'delete_aidtrackingpost'),
(100,'Can view aid tracking post',28,'view_aidtrackingpost'),
(101,'Can add fund transaction',29,'add_fundtransaction'),
(102,'Can change fund transaction',29,'change_fundtransaction'),
(103,'Can delete fund transaction',29,'delete_fundtransaction'),
(104,'Can view fund transaction',29,'view_fundtransaction'),
(105,'Can add organization fund report',30,'add_organizationfundreport'),
(106,'Can change organization fund report',30,'change_organizationfundreport'),
(107,'Can delete organization fund report',30,'delete_organizationfundreport'),
(108,'Can view organization fund report',30,'view_organizationfundreport'),
(109,'Can add transaction archive',31,'add_transactionarchive'),
(110,'Can change transaction archive',31,'change_transactionarchive'),
(111,'Can delete transaction archive',31,'delete_transactionarchive'),
(112,'Can view transaction archive',31,'view_transactionarchive'),
(113,'Can add attendance',32,'add_attendance'),
(114,'Can change attendance',32,'change_attendance'),
(115,'Can delete attendance',32,'delete_attendance'),
(116,'Can view attendance',32,'view_attendance'),
(117,'Can add access session',33,'add_accesssession'),
(118,'Can change access session',33,'change_accesssession'),
(119,'Can delete access session',33,'delete_accesssession'),
(120,'Can view access session',33,'view_accesssession'),
(121,'Can add membership fee',4,'add_membershipfee'),
(122,'Can change membership fee',4,'change_membershipfee'),
(123,'Can delete membership fee',4,'delete_membershipfee'),
(124,'Can view membership fee',4,'view_membershipfee'),
(125,'Can add death aid',3,'add_deathaid'),
(126,'Can change death aid',3,'change_deathaid'),
(127,'Can delete death aid',3,'delete_deathaid'),
(128,'Can view death aid',3,'view_deathaid'),
(129,'Can add contribution',34,'add_contribution'),
(130,'Can change contribution',34,'change_contribution'),
(131,'Can delete contribution',34,'delete_contribution'),
(132,'Can view contribution',34,'view_contribution'),
(133,'Can add push subscription',35,'add_pushsubscription'),
(134,'Can change push subscription',35,'change_pushsubscription'),
(135,'Can delete push subscription',35,'delete_pushsubscription'),
(136,'Can view push subscription',35,'view_pushsubscription'),
(137,'Can add member registration request',1,'add_memberregistrationrequest'),
(138,'Can change member registration request',1,'change_memberregistrationrequest'),
(139,'Can delete member registration request',1,'delete_memberregistrationrequest'),
(140,'Can view member registration request',1,'view_memberregistrationrequest'),
(141,'Can add officer user',36,'add_officeruser'),
(142,'Can change officer user',36,'change_officeruser'),
(143,'Can delete officer user',36,'delete_officeruser'),
(144,'Can view officer user',36,'view_officeruser'),
(145,'Can add transaction verification',37,'add_transactionverification'),
(146,'Can change transaction verification',37,'change_transactionverification'),
(147,'Can delete transaction verification',37,'delete_transactionverification'),
(148,'Can view transaction verification',37,'view_transactionverification'),
(149,'Can add revision log',38,'add_revisionlog'),
(150,'Can change revision log',38,'change_revisionlog'),
(151,'Can delete revision log',38,'delete_revisionlog'),
(152,'Can view revision log',38,'view_revisionlog'),
(153,'Can add member ledger',39,'add_memberledger'),
(154,'Can change member ledger',39,'change_memberledger'),
(155,'Can delete member ledger',39,'delete_memberledger'),
(156,'Can view member ledger',39,'view_memberledger'),
(157,'Can add minutes',40,'add_minutes'),
(158,'Can change minutes',40,'change_minutes'),
(159,'Can delete minutes',40,'delete_minutes'),
(160,'Can view minutes',40,'view_minutes'),
(161,'Can add event',41,'add_event'),
(162,'Can change event',41,'change_event'),
(163,'Can delete event',41,'delete_event'),
(164,'Can view event',41,'view_event'),
(165,'Can add document',42,'add_document'),
(166,'Can change document',42,'change_document'),
(167,'Can delete document',42,'delete_document'),
(168,'Can view document',42,'view_document'),
(169,'Can add announcement',43,'add_announcement'),
(170,'Can change announcement',43,'change_announcement'),
(171,'Can delete announcement',43,'delete_announcement'),
(172,'Can view announcement',43,'view_announcement'),
(173,'Can add certificate',44,'add_certificate'),
(174,'Can change certificate',44,'change_certificate'),
(175,'Can delete certificate',44,'delete_certificate'),
(176,'Can view certificate',44,'view_certificate'),
(177,'Can add certificate settings',45,'add_certificatesettings'),
(178,'Can change certificate settings',45,'change_certificatesettings'),
(179,'Can delete certificate settings',45,'delete_certificatesettings'),
(180,'Can view certificate settings',45,'view_certificatesettings'),
(181,'Can add document pin',46,'add_documentpin'),
(182,'Can change document pin',46,'change_documentpin'),
(183,'Can delete document pin',46,'delete_documentpin'),
(184,'Can view document pin',46,'view_documentpin'),
(185,'Can add document activity',47,'add_documentactivity'),
(186,'Can change document activity',47,'change_documentactivity'),
(187,'Can delete document activity',47,'delete_documentactivity'),
(188,'Can view document activity',47,'view_documentactivity'),
(189,'Can add category',48,'add_category'),
(190,'Can change category',48,'change_category'),
(191,'Can delete category',48,'delete_category'),
(192,'Can view category',48,'view_category');

/*Table structure for table `auth_user` */

DROP TABLE IF EXISTS `auth_user`;

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

/*Data for the table `auth_user` */

/*Table structure for table `auth_user_groups` */

DROP TABLE IF EXISTS `auth_user_groups`;

CREATE TABLE `auth_user_groups` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL,
  `group_id` int(11) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `auth_user_groups_user_id_group_id_94350c0c_uniq` (`user_id`,`group_id`),
  KEY `auth_user_groups_group_id_97559544_fk_auth_group_id` (`group_id`),
  CONSTRAINT `auth_user_groups_group_id_97559544_fk_auth_group_id` FOREIGN KEY (`group_id`) REFERENCES `auth_group` (`id`),
  CONSTRAINT `auth_user_groups_user_id_6a12ed8b_fk_auth_user_id` FOREIGN KEY (`user_id`) REFERENCES `auth_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `auth_user_groups` */

/*Table structure for table `auth_user_user_permissions` */

DROP TABLE IF EXISTS `auth_user_user_permissions`;

CREATE TABLE `auth_user_user_permissions` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL,
  `permission_id` int(11) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `auth_user_user_permissions_user_id_permission_id_14a6b632_uniq` (`user_id`,`permission_id`),
  KEY `auth_user_user_permi_permission_id_1fbb5f2c_fk_auth_perm` (`permission_id`),
  CONSTRAINT `auth_user_user_permi_permission_id_1fbb5f2c_fk_auth_perm` FOREIGN KEY (`permission_id`) REFERENCES `auth_permission` (`id`),
  CONSTRAINT `auth_user_user_permissions_user_id_a95ead1b_fk_auth_user_id` FOREIGN KEY (`user_id`) REFERENCES `auth_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `auth_user_user_permissions` */

/*Table structure for table `backup_job` */

DROP TABLE IF EXISTS `backup_job`;

CREATE TABLE `backup_job` (
  `job_id` int(11) NOT NULL AUTO_INCREMENT,
  `backup_type` varchar(20) NOT NULL,
  `backup_status` varchar(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `db_dump_path` varchar(500) DEFAULT NULL,
  `media_archive_path` varchar(500) DEFAULT NULL,
  `metadata_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`metadata_json`)),
  PRIMARY KEY (`job_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `backup_job` */

/*Table structure for table `bylaws_files` */

DROP TABLE IF EXISTS `bylaws_files`;

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
  PRIMARY KEY (`bylaws_file_id`),
  KEY `bylaws_files_uploaded_by_user_id__a1f6690c_fk_OFFICER_U` (`uploaded_by_user_id_FK`),
  CONSTRAINT `bylaws_files_uploaded_by_user_id__a1f6690c_fk_OFFICER_U` FOREIGN KEY (`uploaded_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `bylaws_files` */

/*Table structure for table `category` */

DROP TABLE IF EXISTS `category`;

CREATE TABLE `category` (
  `category_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`category_id_PK`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=13 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `category` */

insert  into `category`(`category_id_PK`,`name`,`created_at`) values 
(1,'Constitution','2026-07-27 10:19:26.210419'),
(2,'By-Laws','2026-07-27 10:19:26.216673'),
(3,'Minutes of Meeting','2026-07-27 10:19:26.219191'),
(4,'Memorandum','2026-07-27 10:19:26.221813'),
(5,'Office Order','2026-07-27 10:19:26.223866'),
(6,'Resolution','2026-07-27 10:19:26.227195'),
(7,'Circular','2026-07-27 10:19:26.230865'),
(8,'Reportss','2026-07-27 10:19:26.233702'),
(9,'Certificatess','2026-07-27 10:19:26.241447'),
(10,'Activity Documents','2026-07-27 10:19:26.244154'),
(11,'Other Files','2026-07-27 10:19:26.247852'),
(12,'hello','2026-07-27 10:22:49.959868');

/*Table structure for table `certificate` */

DROP TABLE IF EXISTS `certificate`;

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
) ENGINE=InnoDB AUTO_INCREMENT=20 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `certificate` */

insert  into `certificate`(`certificate_id_PK`,`certificate_number`,`pdf_file`,`email_status`,`email_sent_at`,`email_error`,`generated_at`,`downloaded_at`,`member_id_FK`,`event_id_FK`) values 
(1,'ISUCauFA-COL-2026-0001','certificates/certificate_ISUCauFA-COL-2026-0001.pdf','Sent','2026-07-28 10:29:27.289153','','2026-07-28 10:29:21.723287',NULL,14,4),
(2,'ISUCauFA-COL-2026-0002','certificates/certificate_ISUCauFA-COL-2026-0002.pdf','Sent','2026-07-28 10:29:34.264404','','2026-07-28 10:29:27.309391',NULL,13,4),
(3,'ISUCauFA-ZXC-2026-0001','certificates/certificate_ISUCauFA-ZXC-2026-0001.pdf','Sent','2026-07-28 10:33:30.032688','','2026-07-28 10:33:26.169059',NULL,14,5),
(4,'ISUCauFA-ZXC-2026-0002','certificates/certificate_ISUCauFA-ZXC-2026-0002.pdf','Sent','2026-07-28 10:33:34.236134','','2026-07-28 10:33:30.040261',NULL,13,5),
(5,'ISUCauFA-FFF-2026-0001','certificates/certificate_ISUCauFA-FFF-2026-0001.pdf','Sent','2026-07-28 10:35:28.853209','','2026-07-28 10:35:24.507087',NULL,13,6),
(6,'ISUCauFA-ATTCV-2026-0001','certificates/certificate_ISUCauFA-ATTCV-2026-0001.pdf','Sent','2026-07-28 10:40:13.199516','','2026-07-28 10:40:08.799632',NULL,13,7),
(7,'ISUCauFA-ATTQWE-2026-0001','certificates/certificate_ISUCauFA-ATTQWE-2026-0001.pdf','Sent','2026-07-28 10:56:16.676514','','2026-07-28 10:56:11.885012',NULL,13,8),
(8,'ISUCauFA-hhATT-2026-0001','certificates/certificate_ISUCauFA-hhATT-2026-0001.pdf','Sent','2026-07-28 11:20:41.216203','','2026-07-28 11:20:35.995975',NULL,13,9),
(9,'ISUCauFA-ATTC-2026-0001','certificates/certificate_ISUCauFA-ATTC-2026-0001.pdf','Sent','2026-07-28 11:34:47.180987','','2026-07-28 11:34:42.098895',NULL,14,11),
(10,'ISUCauFA-ATTC-2026-0002','certificates/certificate_ISUCauFA-ATTC-2026-0002.pdf','Sent','2026-07-28 11:34:54.391492','','2026-07-28 11:34:49.867133',NULL,13,11),
(11,'ISUCauFA-ATT-2026-0001','certificates/certificate_ISUCauFA-ATT-2026-0001.pdf','Sent','2026-07-28 12:02:09.725235','','2026-07-28 12:02:02.124210',NULL,13,12),
(12,'ISUCauFA-ATTERT-2026-0001','certificates/certificate_ISUCauFA-ATTERT-2026-0001_142joe2.pdf','Sent','2026-07-28 13:39:16.753405','','2026-07-28 13:39:05.042607',NULL,14,13),
(13,'ISUCauFA-ATTERT-2026-0002','certificates/certificate_ISUCauFA-ATTERT-2026-0002_142joe.pdf','Sent','2026-07-28 13:39:31.366997','','2026-07-28 13:39:20.877360',NULL,13,13),
(14,'ISUCauFA-ATT-2026-0002','certificates/certificate_ISUCauFA-ATT-2026-0002_142joe2.pdf','Sent','2026-07-28 13:45:41.499396','','2026-07-28 13:45:30.308692',NULL,14,14),
(15,'ISUCauFA-ATT-2026-0003','certificates/certificate_ISUCauFA-ATT-2026-0003_142joe2.pdf','Sent','2026-07-28 13:49:13.301313','','2026-07-28 13:49:01.198615',NULL,14,15),
(16,'ISUCauFA-ATT-2026-0004','certificates/certificate_ISUCauFA-ATT-2026-0004_142joe.pdf','Sent','2026-07-28 13:49:29.721827','','2026-07-28 13:49:18.787404',NULL,13,15),
(17,'ISUCauFA-ATTjjjj-2026-0001','certificates/certificate_ISUCauFA-ATTjjjj-2026-0001_142joe2.pdf','Sent','2026-07-28 14:14:23.691483','','2026-07-28 14:14:11.923868',NULL,14,16),
(18,'ISUCauFA-ATTfinal?>-2026-0001','certificates/certificate_ISUCauFA-ATTfinal-2026-0001_142joe2.pdf','Sent','2026-07-28 14:15:46.611281','','2026-07-28 14:15:35.747697',NULL,14,17),
(19,'ISUCauFA-ATTfinal?>-2026-0002','certificates/certificate_ISUCauFA-ATTfinal-2026-0002_142joe.pdf','Sent','2026-07-28 14:16:03.504166','','2026-07-28 14:15:52.356493',NULL,13,17);

/*Table structure for table `certificate_settings` */

DROP TABLE IF EXISTS `certificate_settings`;

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
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `certificate_settings` */

insert  into `certificate_settings`(`settings_id_PK`,`president_name`,`president_position`,`president_signature`,`secretary_name`,`secretary_position`,`secretary_signature`,`faculty_regent_name`,`faculty_regent_position`,`faculty_regent_signature`,`organization_logo`,`header_text`,`footer_text`,`updated_at`) values 
(1,'JOHN PAUL VERSOZA, PHD','ISUCauFA PRESIDENT','','JASMINE ROTUGAL, MIT','ISUCauFA, Inc. SECRETARY','','','Faculty Regent','','','REPUBLIC OF THE PHILIPPINES','','2026-07-28 14:13:43.590385');

/*Table structure for table `claimant` */

DROP TABLE IF EXISTS `claimant`;

CREATE TABLE `claimant` (
  `claimant_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `full_name` varchar(255) NOT NULL,
  `contact_number` varchar(50) DEFAULT NULL,
  `relationship_to_member` varchar(100) NOT NULL,
  `authorization_status` varchar(50) NOT NULL,
  `member_id_FK` int(11) NOT NULL,
  `relationship_group` varchar(20) NOT NULL,
  PRIMARY KEY (`claimant_id_PK`),
  KEY `CLAIMANT_member_id_FK_348a8f79_fk_MEMBER_member_id_PK` (`member_id_FK`),
  CONSTRAINT `CLAIMANT_member_id_FK_348a8f79_fk_MEMBER_member_id_PK` FOREIGN KEY (`member_id_FK`) REFERENCES `member` (`member_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `claimant` */

/*Table structure for table `contribution` */

DROP TABLE IF EXISTS `contribution`;

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
  KEY `CONTRIBUTION_updated_by_user_id_F_158d64bf_fk_OFFICER_U` (`updated_by_user_id_FK`),
  CONSTRAINT `CONTRIBUTION_aid_tracking_post_id_ca2a2aac_fk_AID_TRACK` FOREIGN KEY (`aid_tracking_post_id_FK`) REFERENCES `aid_tracking_post` (`post_id_PK`),
  CONSTRAINT `CONTRIBUTION_member_id_FK_ed361721_fk_MEMBER_member_id_PK` FOREIGN KEY (`member_id_FK`) REFERENCES `member` (`member_id_PK`),
  CONSTRAINT `CONTRIBUTION_updated_by_user_id_F_158d64bf_fk_OFFICER_U` FOREIGN KEY (`updated_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `contribution` */

/*Table structure for table `death_aid` */

DROP TABLE IF EXISTS `death_aid`;

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
  KEY `DEATH_AID_released_by_user_id_FK_c16b5c5b` (`released_by_user_id_FK`),
  CONSTRAINT `DEATH_AID_auditor_verified_by__80ca4f33_fk_OFFICER_U` FOREIGN KEY (`auditor_verified_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`),
  CONSTRAINT `DEATH_AID_claimant_id_FK_f0b13e0c_fk_CLAIMANT_claimant_id_PK` FOREIGN KEY (`claimant_id_FK`) REFERENCES `claimant` (`claimant_id_PK`),
  CONSTRAINT `DEATH_AID_member_id_FK_ba2eae1b_fk_MEMBER_member_id_PK` FOREIGN KEY (`member_id_FK`) REFERENCES `member` (`member_id_PK`),
  CONSTRAINT `DEATH_AID_president_decided_by_bcc1b2ff_fk_OFFICER_U` FOREIGN KEY (`president_decided_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`),
  CONSTRAINT `DEATH_AID_treasurer_validated__54e09fac_fk_OFFICER_U` FOREIGN KEY (`treasurer_validated_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `death_aid` */

/*Table structure for table `department` */

DROP TABLE IF EXISTS `department`;

CREATE TABLE `department` (
  `department_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `code` varchar(50) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `head_officer_id_FK` int(11) DEFAULT NULL,
  PRIMARY KEY (`department_id_PK`),
  UNIQUE KEY `code` (`code`),
  KEY `DEPARTMENT_head_officer_id_FK_9ade364b_fk_OFFICER_U` (`head_officer_id_FK`),
  CONSTRAINT `DEPARTMENT_head_officer_id_FK_9ade364b_fk_OFFICER_U` FOREIGN KEY (`head_officer_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `department` */

/*Table structure for table `django_admin_log` */

DROP TABLE IF EXISTS `django_admin_log`;

CREATE TABLE `django_admin_log` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `action_time` datetime(6) NOT NULL,
  `object_id` longtext DEFAULT NULL,
  `object_repr` varchar(200) NOT NULL,
  `action_flag` smallint(5) unsigned NOT NULL CHECK (`action_flag` >= 0),
  `change_message` longtext NOT NULL,
  `content_type_id` int(11) DEFAULT NULL,
  `user_id` int(11) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `django_admin_log_content_type_id_c4bce8eb_fk_django_co` (`content_type_id`),
  KEY `django_admin_log_user_id_c564eba6_fk_auth_user_id` (`user_id`),
  CONSTRAINT `django_admin_log_content_type_id_c4bce8eb_fk_django_co` FOREIGN KEY (`content_type_id`) REFERENCES `django_content_type` (`id`),
  CONSTRAINT `django_admin_log_user_id_c564eba6_fk_auth_user_id` FOREIGN KEY (`user_id`) REFERENCES `auth_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `django_admin_log` */

/*Table structure for table `django_content_type` */

DROP TABLE IF EXISTS `django_content_type`;

CREATE TABLE `django_content_type` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `app_label` varchar(100) NOT NULL,
  `model` varchar(100) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `django_content_type_app_label_model_76bd3d3b_uniq` (`app_label`,`model`)
) ENGINE=InnoDB AUTO_INCREMENT=49 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `django_content_type` */

insert  into `django_content_type`(`id`,`app_label`,`model`) values 
(6,'admin','logentry'),
(8,'auth','group'),
(9,'auth','permission'),
(7,'auth','user'),
(10,'contenttypes','contenttype'),
(33,'core_system','accesssession'),
(28,'core_system','aidtrackingpost'),
(43,'core_system','announcement'),
(32,'core_system','attendance'),
(21,'core_system','auditfindingsreport'),
(14,'core_system','backupjob'),
(16,'core_system','bylawsfile'),
(48,'core_system','category'),
(44,'core_system','certificate'),
(45,'core_system','certificatesettings'),
(19,'core_system','claimant'),
(34,'core_system','contribution'),
(3,'core_system','deathaid'),
(20,'core_system','department'),
(42,'core_system','document'),
(47,'core_system','documentactivity'),
(46,'core_system','documentpin'),
(41,'core_system','event'),
(27,'core_system','financialdocumentarchive'),
(29,'core_system','fundtransaction'),
(17,'core_system','globalaudittrail'),
(23,'core_system','loginattemptlog'),
(2,'core_system','medicalaid'),
(26,'core_system','member'),
(39,'core_system','memberledger'),
(1,'core_system','memberregistrationrequest'),
(4,'core_system','membershipfee'),
(40,'core_system','minutes'),
(5,'core_system','monthlydues'),
(24,'core_system','notification'),
(36,'core_system','officeruser'),
(30,'core_system','organizationfundreport'),
(13,'core_system','outgoingemail'),
(18,'core_system','payrollbatch'),
(15,'core_system','payrolldeduction'),
(35,'core_system','pushsubscription'),
(38,'core_system','revisionlog'),
(12,'core_system','sensitivereadlog'),
(22,'core_system','supportingproof'),
(25,'core_system','systemsetting'),
(31,'core_system','transactionarchive'),
(37,'core_system','transactionverification'),
(11,'sessions','session');

/*Table structure for table `django_migrations` */

DROP TABLE IF EXISTS `django_migrations`;

CREATE TABLE `django_migrations` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `app` varchar(255) NOT NULL,
  `name` varchar(255) NOT NULL,
  `applied` datetime(6) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=108 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `django_migrations` */

insert  into `django_migrations`(`id`,`app`,`name`,`applied`) values 
(1,'contenttypes','0001_initial','2026-07-26 00:28:55.716152'),
(2,'auth','0001_initial','2026-07-26 00:28:55.730975'),
(3,'admin','0001_initial','2026-07-26 00:28:55.740526'),
(4,'admin','0002_logentry_remove_auto_add','2026-07-26 00:28:55.749717'),
(5,'admin','0003_logentry_add_action_flag_choices','2026-07-26 00:28:55.756682'),
(6,'contenttypes','0002_remove_content_type_name','2026-07-26 00:28:55.773252'),
(7,'auth','0002_alter_permission_name_max_length','2026-07-26 00:28:55.782308'),
(8,'auth','0003_alter_user_email_max_length','2026-07-26 00:28:55.794346'),
(9,'auth','0004_alter_user_username_opts','2026-07-26 00:28:55.802916'),
(10,'auth','0005_alter_user_last_login_null','2026-07-26 00:28:55.811745'),
(11,'auth','0006_require_contenttypes_0002','2026-07-26 00:28:55.821835'),
(12,'auth','0007_alter_validators_add_error_messages','2026-07-26 00:28:55.826198'),
(13,'auth','0008_alter_user_username_max_length','2026-07-26 00:28:55.829217'),
(14,'auth','0009_alter_user_last_name_max_length','2026-07-26 00:28:55.834216'),
(15,'auth','0010_alter_group_name_max_length','2026-07-26 00:28:55.838387'),
(16,'auth','0011_update_proxy_permissions','2026-07-26 00:28:55.843192'),
(17,'auth','0012_alter_user_first_name_max_length','2026-07-26 00:28:55.848893'),
(18,'core_system','0001_initial','2026-07-26 00:28:55.852428'),
(19,'core_system','0002_alter_auditfindingsreport_prepared_by_user_id_fk','2026-07-26 00:28:55.857369'),
(20,'core_system','0003_monthlydues_payment_date','2026-07-26 00:28:55.861388'),
(21,'core_system','0004_transactionverification','2026-07-26 00:28:55.865398'),
(22,'core_system','0005_medicalaid_requested_amount','2026-07-26 00:28:55.869572'),
(23,'core_system','0006_medicalaid_hospital_name','2026-07-26 00:28:55.874148'),
(24,'core_system','0007_alter_membershipfee_unique_together','2026-07-26 00:28:55.883193'),
(25,'core_system','0008_clean_duplicate_membership_fees','2026-07-26 00:28:55.892860'),
(26,'core_system','0008_merge','2026-07-26 00:28:55.903060'),
(27,'core_system','0009_supportingproof','2026-07-26 00:28:55.912543'),
(28,'core_system','0010_revision_log_table','2026-07-26 00:28:55.922547'),
(29,'core_system','0011_member_department_member_employee_id_member_position_and_more','2026-07-26 00:28:55.931608'),
(30,'core_system','0012_membershipfee_month_covered','2026-07-26 00:28:55.940587'),
(31,'core_system','0013_membershipfee_payment_method','2026-07-26 00:28:55.946737'),
(32,'core_system','0014_auditorpaymentverification','2026-07-26 00:28:55.955746'),
(33,'core_system','0015_audit_aid_verification_table','2026-07-26 00:28:55.960768'),
(34,'core_system','0016_alter_auditoraidverification_auditor_aid_verification_id_pk','2026-07-26 00:28:55.968017'),
(35,'core_system','0017_transactionarchive','2026-07-26 00:28:55.973073'),
(36,'core_system','0018_add_global_audit_trail','2026-07-26 00:28:55.977600'),
(37,'core_system','0019_aidtrackingpost_contribution','2026-07-26 00:28:55.982128'),
(38,'core_system','0020_merge_audit_tables','2026-07-26 00:28:55.987136'),
(39,'core_system','0021_drop_old_audit_tables','2026-07-26 00:28:55.991666'),
(40,'core_system','0022_push_subscription','2026-07-26 00:28:55.996139'),
(41,'core_system','0023_death_aid_funeral_details','2026-07-26 00:28:56.000672'),
(42,'core_system','0024_death_aid_add_relationship_group','2026-07-26 00:28:56.004203'),
(43,'core_system','0025_medicalaid_hospital_date','2026-07-26 00:28:56.010478'),
(44,'core_system','0026_sensitive_read_log','2026-07-26 00:28:56.014594'),
(45,'core_system','0027_backfill_medical_aid_validated_amount','2026-07-26 00:28:56.025537'),
(46,'core_system','0028_department_and_more','2026-07-26 00:28:56.031633'),
(47,'core_system','0029_backfill_department_fk','2026-07-26 00:28:56.035633'),
(48,'core_system','0030_systemsetting','2026-07-26 00:28:56.040243'),
(49,'core_system','0031_seed_system_settings','2026-07-26 00:28:56.044258'),
(50,'core_system','0032_notification_category_notification_channel_and_more','2026-07-26 00:28:56.048519'),
(51,'core_system','0033_transactionarchive_fiscal_term_and_more','2026-07-26 00:28:56.052839'),
(52,'core_system','0034_aidtrackingpost_finish_skip_remaining_and_more','2026-07-26 00:28:56.056846'),
(53,'core_system','0035_outbound_email','2026-07-26 00:28:56.061307'),
(54,'core_system','0036_rename_outbound_email_status_scheduled_idx_outbound_em_status_87763e_idx','2026-07-26 00:28:56.078874'),
(55,'core_system','0037_delete_outboundemail','2026-07-26 00:28:56.088390'),
(56,'core_system','0038_alter_medicalaid_hospital_date','2026-07-26 00:28:56.096991'),
(57,'core_system','0039_remove_membershipfee_month_covered','2026-07-26 00:28:56.102033'),
(58,'core_system','0040_backfill_membership_fees','2026-07-26 00:28:56.118192'),
(59,'core_system','0041_payrollbatch_fundtransaction_payrolldeduction','2026-07-26 00:28:56.140700'),
(60,'core_system','0042_remove_aidtrackingpost_finish_skip_remaining_and_more','2026-07-26 00:28:56.150276'),
(61,'core_system','0043_aidtrackingpost_finish_status_paid_with_funds','2026-07-26 00:28:56.158488'),
(62,'core_system','0044_alter_fundtransaction_source_type_and_more','2026-07-26 00:28:56.165525'),
(63,'core_system','0045_alter_member_employee_id','2026-07-26 00:28:56.186361'),
(64,'core_system','0046_outgoingemail','2026-07-26 00:28:56.199366'),
(65,'core_system','0047_aidtrackingpost_finish_paid_with_funds','2026-07-26 00:28:56.208994'),
(66,'core_system','0048_alter_aidtrackingpost_finish_status','2026-07-26 00:28:56.215578'),
(67,'core_system','0049_add_file_name_type_to_financialdocumentarchive','2026-07-26 00:28:56.222641'),
(68,'core_system','0050_backfill_bylaws_file_metadata','2026-07-26 00:28:56.229160'),
(69,'core_system','0051_bylawsfile','2026-07-26 00:28:56.235517'),
(70,'core_system','0052_migrate_bylaws_to_bylawsfile','2026-07-26 00:28:56.243327'),
(71,'core_system','0053_officeruser_mfa_enabled','2026-07-26 00:28:56.254877'),
(72,'core_system','0054_officeruser_last_mfa_email_sent_at','2026-07-26 00:28:56.263922'),
(73,'core_system','0055_accesssession_last_verified_location_and_more','2026-07-26 00:28:56.271125'),
(74,'core_system','0056_add_officeruser_department_fk','2026-07-26 00:28:56.277224'),
(75,'core_system','0057_seed_departments','2026-07-26 00:28:56.285521'),
(76,'core_system','0058_add_officeruser_email','2026-07-26 00:28:56.292181'),
(77,'core_system','0059_add_deduction_sheet_fields','2026-07-26 00:28:56.297244'),
(78,'core_system','0060_add_deduction_remittance_fields','2026-07-26 00:28:56.306436'),
(79,'core_system','0061_increase_audit_trail_action_max_length','2026-07-26 00:28:56.312729'),
(80,'core_system','0062_add_sensitive_read_log_device_info','2026-07-26 00:28:56.318766'),
(81,'core_system','0063_add_contribution_recorded_status','2026-07-26 00:28:56.324384'),
(82,'core_system','0064_add_member_registration_request','2026-07-26 00:28:56.331413'),
(83,'core_system','0065_fix_officer_member_type','2026-07-26 00:28:56.338336'),
(84,'core_system','0067_memberregistrationrequest_password_hash','2026-07-26 00:28:56.363219'),
(85,'core_system','0068_member_profile_picture','2026-07-26 00:28:56.374597'),
(86,'core_system','0069_rename_sensitive_r_table_n_c95688_idx_sensitive_r_module_b2b1eb_idx_and_more','2026-07-26 00:28:56.385878'),
(87,'core_system','0070_registration_workflow_fields','2026-07-26 00:28:56.398494'),
(88,'core_system','0071_rename_sensitive_r_table_n_c95688_idx_sensitive_r_module_b2b1eb_idx_and_more','2026-07-26 00:28:56.408296'),
(89,'core_system','0073_add_is_read_to_notification','2026-07-26 00:28:56.416959'),
(90,'core_system','0074_add_approval_fields_to_monthly_dues','2026-07-26 00:28:56.422574'),
(91,'core_system','0075_add_member_ledger_model','2026-07-26 00:28:56.429114'),
(92,'core_system','0076_add_attendance_model','2026-07-26 00:28:56.436633'),
(93,'core_system','0077_add_member_onboarding_fields','2026-07-26 00:28:56.452110'),
(94,'core_system','0078_rename_sensitive_r_table_n_c95688_idx_sensitive_r_module_b2b1eb_idx_and_more','2026-07-26 00:28:56.463866'),
(95,'sessions','0001_initial','2026-07-26 00:28:56.475488'),
(96,'core_system','0079_fix_attendance_member_fk','2026-07-26 00:44:30.760907'),
(97,'core_system','0080_announcement_document_event_minutes_and_more','2026-07-26 00:59:26.739987'),
(99,'core_system','0081_add_missing_secretary_fks','2026-07-26 01:18:35.209632'),
(100,'core_system','0082_certificate_certificatesettings_and_more','2026-07-26 10:23:21.257382'),
(101,'core_system','0083_certificate_certificatesettings_and_more','2026-07-27 08:34:08.891392'),
(102,'core_system','0084_add_certificate_fk_columns','2026-07-27 09:18:25.371892'),
(104,'core_system','0085_document_pin_activity','2026-07-27 10:18:05.807330'),
(105,'core_system','0086_category','2026-07-27 10:19:26.262961'),
(106,'core_system','0087_rename_sensitive_r_table_n_c95688_idx_sensitive_r_module_b2b1eb_idx_and_more','2026-07-27 11:35:18.772323'),
(107,'core_system','0088_eventtype','2026-07-28 10:09:44.321842');

/*Table structure for table `django_session` */

DROP TABLE IF EXISTS `django_session`;

CREATE TABLE `django_session` (
  `session_key` varchar(40) NOT NULL,
  `session_data` longtext NOT NULL,
  `expire_date` datetime(6) NOT NULL,
  PRIMARY KEY (`session_key`),
  KEY `django_session_expire_date_a5c62663` (`expire_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `django_session` */

insert  into `django_session`(`session_key`,`session_data`,`expire_date`) values 
('16ztkthd7yyiue8ubt9ahll79p3ze7qj','eyJhY2Nlc3NfdG9rZW4iOiJINi1TX3AwZTVTSHFkb3B2SkR3aEFGeUt3eEwyUlJ4TERGZlRkVkY1eHF3Iiwib2ZmaWNlcl9pZCI6MjksInJvbGUiOiJNZW1iZXIifQ:1wna0x:IAPKC5i7BTjAL_xDnWN1PrBu3jH_t6fwtDOOOIBmEZ0','2026-08-08 10:53:55.336179'),
('1qhasis6c7ov4rbrdm5zugd5tiifnyqu','eyJvZmZpY2VyX2lkIjoyNCwicm9sZSI6IlRyZWFzdXJlciIsImFjY2Vzc190b2tlbiI6InpJMWhLbGRfN0FyRXczQXpmaWxLOGpzb3BRY1hFZ0hNWmdOcGN2TG03VWsifQ:1wnZX6:ochtrL90kU2Eu6lc6n3avNjS78DJ0ODrNeD4RjUiN3U','2026-08-08 10:23:04.495524'),
('6ypqqiqolwue8yn0ljhw4b9tw4et6k36','eyJhY2Nlc3NfdG9rZW4iOiI1dFBraGttUnlyc29FcTY0TS1YVG5HSUtKaEFiMGlhMmpFbEtnYnM4RlRzIiwib2ZmaWNlcl9pZCI6NDMsInJvbGUiOiJBdWRpdG9yIn0:1woK31:icSUS16g7SxzMfdv-xAYS1Xan_q2dMplyBsjvJFiQf0','2026-08-10 12:03:07.209227'),
('b4c3vbo0azjcems5g5wfhm32pt2w2pi2','eyJhY2Nlc3NfdG9rZW4iOiJtVUxhc0VDcVJ6NElocGc3c25fbS1RekxuY3dfNHNLTEtrZTduLWd1aUtFIiwib2ZmaWNlcl9pZCI6MzgsInJvbGUiOiJNZW1iZXIifQ:1wnwWM:kBl9S5hhL6Z8FhuQc5LXCeJin3X01BCqNlYBWS6qpVo','2026-08-09 10:55:50.146405'),
('cgu4828zz7sathp7ufo10sararv1nisi','.eJwljsFqwzAQRH9F6NwGpzRt8K2BNqdADCk5irU8jpfIUlhJiU3pv1dpTgvDmzf7o8eezEVgKKfBpHCG17X-vuKrwmE1bXevS9q3z-3aHZdpsxuP9Lm22-G0aZw5NM271U__itD3bCGGO12_rB5ZjhBPI4qQcscpSIFNRIwcvMF0YZl1_VZVDxwjsTM3Es_-VDof6grhoqVUeGVDB3WjqMgJqJtVhE9KYMtx80LtHShC2QH2rOaQRbFvw7S4b9717DkxJZQHk2T8_gG2qFgz:1wnaDe:6hhImWzt_2oyeeX4RaU-sFL0pSTtgbGG4Xt-EWFaApo','2026-07-25 11:17:02.636551'),
('hisiu3qnvn9ax1xyoi7p7o8atyqwkozl','.eJwlzL0KwjAUQOF3yexQlBabsYOCCLoUqcslNjd4SZub5odaxHe36Ho4fG8xGgU-IKicnpDYohNSPLr90FwPmXhnJ9s1YzXxrb_cjT-d27oM2rVcH_WS5llsfgQbQz0GIC3ktvy3HDE4NeIKqqwpcVhniBgjsQN8eQqLkFVRfL7RAS_F:1wnaQy:DUUyuq3H6-4PrvTnh5GmzoELZWiPxBr2XMme31sggE8','2026-07-25 11:30:48.126652'),
('hj3upri84avvgabbk23wpmi46l6pq32j','eyJvZmZpY2VyX2lkIjo0NSwicm9sZSI6Ik1lbWJlciIsImFjY2Vzc190b2tlbiI6IlZnYzZldzBSX25ocEhqdFZ6UW8tOXdzQ2Q4b0NTTEZOcVpqR2RZOHRFVVkifQ:1wodqQ:j-QL7ZWb-ldftSE3SlgH48xfC4wFjZ8b8FEGKWaNsDk','2026-08-11 09:11:26.853777'),
('hvdwf5uqfxp77bjnsz8xpe2o6kw4sqqu','eyJhY2Nlc3NfdG9rZW4iOiJ5WHdSZGxFSm9Xc0l5NjBaWWk4c2xCeHlscW1Nck5KZW1tSGxYMDUwUWVNIiwib2ZmaWNlcl9pZCI6NDUsInJvbGUiOiJNZW1iZXIifQ:1woKZY:Mew_DjcYLkzEApWEF5FQqtTAvSY5i3RjrJwEQ3v-26s','2026-08-10 12:36:44.551944'),
('lh10zj9ya3ek6cmqquqazlgrb42gt7lp','eyJhY2Nlc3NfdG9rZW4iOiJreEhub2RmUktfTEJCYWl4dVNKOFJwLWZIQ3NUdFNjd1pYS0JvZ1ZjeXpZIiwib2ZmaWNlcl9pZCI6MjcsInJvbGUiOiJNZW1iZXIifQ:1wnZyf:IiWL9cF46rovdHiUuR_brdkeDv_axThF5gafVtHczDg','2026-08-08 10:51:33.899559'),
('lttnskq2apj8g8ypqbr6nth65acwifla','eyJhY2Nlc3NfdG9rZW4iOiJOOUpvQzNKdkRWak1PaW8wcUVBLTlSUjhWalVGb3RQa0JwY1hjZnJMQ1lnIiwib2ZmaWNlcl9pZCI6MjUsInJvbGUiOiJBdWRpdG9yIn0:1wnacy:4tqQlLwqyTJwT4qxxMyrfd1E0IZWwb4qRE7oXvjwHz8','2026-08-08 11:33:12.406158'),
('mbh1wche5ndef5nuqnki8pbafevn36tz','eyJfc2Vzc2lvbl9leHBpcnkiOjYwMCwiYWNjZXNzX3Rva2VuIjoidzRnNUJjV1Z0VGRrYkE0TXp6dDQ1bEtUNlIxZC1XcldNTkxyLWJ3a29hRSIsIm9mZmljZXJfaWQiOjM3LCJyb2xlIjoiTWVtYmVyIn0:1wnvmB:RB-mEw_EmRM_dS74VQq0_1tJ1I2WApLoj9ZEMK9GJGk','2026-07-26 10:18:07.596543'),
('nhc2qb0ghq9ez6r2vcebf38zpo90dr8j','eyJvZmZpY2VyX2lkIjo0NCwicm9sZSI6IlNlY3JldGFyeSIsImFjY2Vzc190b2tlbiI6Im5wRmxZYkhUVHV5eVJkNmYtNUZyS2Exam9WMlUzSFItcFJyOFlCWV81WWsifQ:1wodoR:jTvuUFVopjHq9BCnCTG6Dg2kgDwXlVnXUIv-Q6dT5y0','2026-08-11 09:09:23.515339'),
('o7wop1us6wzzu4v8o63o8jh0z0vbb0ct','eyJvZmZpY2VyX2lkIjo0NSwicm9sZSI6Ik1lbWJlciIsImFjY2Vzc190b2tlbiI6InhYQ0phS1lwSkJPdUdzUmIxWjVLdjRLaUFJU2ZQYjVLQzh3aElzdVo3MVEifQ:1wp1li:ZMsSSN_KtSsVy3nS0cQqy4e4zmDRcVMs72n4bevBn34','2026-08-12 10:44:10.021306'),
('p2m9ui6j4adug1t90fl2n34afz5wtfnr','eyJvZmZpY2VyX2lkIjozMCwicm9sZSI6IlNlY3JldGFyeSIsImFjY2Vzc190b2tlbiI6IlJiOEc1N25wbmxVczRXUmxGLWhINGZLNHdBTjRjQXlxVjAxYlpoeG16a2sifQ:1wnvy9:UMQG-oWiqVWX3c3Sz2xW4WFpJsKerRUIZxDld2ktwAA','2026-08-09 10:20:29.467288'),
('spxebksspdax0jrj772qfpzpx1yjfsry','eyJvZmZpY2VyX2lkIjo0NSwicm9sZSI6Ik1lbWJlciIsImFjY2Vzc190b2tlbiI6IlBNWlFuUmx4Rm83ejZ2Y0pvWXNxUW9kbmREWXphQkx3NEV4MlNRRjB3VVkifQ:1wp19w:EGYAelYHEaVQghshtcIW3dziNLNaLPpXkU--UGtGKRg','2026-08-12 10:05:08.989946'),
('vi3rim4oypbxx094xgz07za7a91owrdt','eyJhY2Nlc3NfdG9rZW4iOiJ5VmsxQjk0dWFTOGJsLWdTLVM4dWVvaUtvUTdMWG55TDNVMzkyWV94ZnpRIiwib2ZmaWNlcl9pZCI6MjMsInJvbGUiOiJQcmVzaWRlbnQifQ:1wnZxw:zrJULlO5ubX0fHt5Z961hj9BbF8YH61u7MxbndmMc4o','2026-08-08 10:50:48.469159'),
('vmuyjctrpd79i86tploq603xp2ftbkfk','eyJvZmZpY2VyX2lkIjoyNSwicm9sZSI6IkF1ZGl0b3IiLCJhY2Nlc3NfdG9rZW4iOiJEaHVrNW9CRnNnSFNBai0zSjcwWDE1ZW0wZFMxMWwzcFhVdzRuQWdubWM0In0:1wnvq6:_X3nBlIQ-6IlPE8K4pDtVsTUP2tsTHgAkAoydAurio8','2026-08-09 10:12:10.342312'),
('wi1ek21g308bnxddmsmzk4im34bajbm7','eyJhY2Nlc3NfdG9rZW4iOiJBdmY4MVU3YXFsQTBTbHJtNVlFTm5uenlUZWZlZVdZdjdfblUzNmJMMUN3Iiwib2ZmaWNlcl9pZCI6MzgsInJvbGUiOiJNZW1iZXIifQ:1wnvxm:u9tfL92eZEA3bTC6UopAaAJAGhprgyOyl-ftx8vBvCw','2026-08-09 10:20:06.362002'),
('ywbwefjrltwdbgkd3ebwyj6dkj3wnzcr','eyJvZmZpY2VyX2lkIjo0NSwicm9sZSI6Ik1lbWJlciIsImFjY2Vzc190b2tlbiI6ImxxLWVCNFpTdFV0YU40cnRhd1RhUmQ5aERHajJrUHd6czNjTUZ3UlNZdTgifQ:1wocqv:jH3HPf-u5T0T8qIFDe1GOhG5YtqB7fRhgrqB5uTgAog','2026-08-11 08:07:53.439939');

/*Table structure for table `document` */

DROP TABLE IF EXISTS `document`;

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
  PRIMARY KEY (`document_id_PK`),
  KEY `DOCUMENT_uploaded_by_user_id__2d5af3d8_fk_OFFICER_U` (`uploaded_by_user_id_FK`),
  CONSTRAINT `DOCUMENT_uploaded_by_user_id__2d5af3d8_fk_OFFICER_U` FOREIGN KEY (`uploaded_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `document` */

insert  into `document`(`document_id_PK`,`title`,`description`,`document_type`,`category`,`keywords`,`tags`,`file_path`,`file_name`,`file_size`,`file_type`,`version`,`uploaded_at`,`retention_period`,`is_archived`,`uploaded_by_user_id_FK`) values 
(1,'hello test certificate','HAHA','Activity Documents','Activity Documents, Certificatess, Constitution','goodzxc','','C:\\Users\\USER\\Downloads\\CAPSTONE_PROJECT-panel-system-dev\\CAPSTONE_PROJECT-panel-system-dev\\media\\documents\\CERTIFICATE.pdf','CERTIFICATE.pdf',481871,'application/pdf','1.0','2026-07-27 10:53:10.434209',NULL,0,30),
(2,'QWEZXCRT','gaga','Constitution','Constitution, hello','yolo','','C:\\Users\\USER\\Downloads\\CAPSTONE_PROJECT-panel-system-dev\\CAPSTONE_PROJECT-panel-system-dev\\media\\documents\\System_Checking_Findings.docx','System_Checking_Findings.docx',13704,'application/vnd.openxmlformats-officedocument.word','1.0','2026-07-27 11:04:12.129960',NULL,0,30),
(3,'cxz','sdfasd','Other Files','Other Files, Reportss, Resolution','paul','','C:\\Users\\USER\\Downloads\\CAPSTONE_PROJECT-panel-system-dev\\CAPSTONE_PROJECT-panel-system-dev\\media\\documents\\ATTENDANCE FORMAT.docx','ATTENDANCE FORMAT.docx',121650,'application/vnd.openxmlformats-officedocument.word','1.0','2026-07-27 11:06:17.068175',NULL,0,30),
(4,'kjkl','GGGG','Memorandum','Memorandum','GGGGg','','C:\\Users\\USER\\Downloads\\CAPSTONE_PROJECT-panel-system-dev\\CAPSTONE_PROJECT-panel-system-dev\\media\\documents\\VON GROUPS.pptx','VON GROUPS.pptx',6672650,'application/vnd.openxmlformats-officedocument.pres','1.0','2026-07-27 11:16:30.402340',NULL,0,30),
(5,'rrrrrrr','hhhhhhhh','By-Laws','By-Laws, Circular, Resolution','gftyu','','C:\\Users\\USER\\Downloads\\CAPSTONE_PROJECT-panel-system-dev\\CAPSTONE_PROJECT-panel-system-dev\\media\\documents\\von and fred DSA act.pdf','von and fred DSA act.pdf',2123147,'application/pdf','1.0','2026-07-27 11:20:11.932516',NULL,0,30);

/*Table structure for table `document_activity` */

DROP TABLE IF EXISTS `document_activity`;

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
  KEY `DOCUMENT_ACTIVITY_officer_id_FK_e46a0d41_fk_OFFICER_U` (`officer_id_FK`),
  CONSTRAINT `DOCUMENT_ACTIVITY_document_id_FK_2c1d21b5_fk_DOCUMENT_` FOREIGN KEY (`document_id_FK`) REFERENCES `document` (`document_id_PK`),
  CONSTRAINT `DOCUMENT_ACTIVITY_officer_id_FK_e46a0d41_fk_OFFICER_U` FOREIGN KEY (`officer_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `document_activity` */

insert  into `document_activity`(`activity_id`,`action`,`officer_name`,`details`,`timestamp`,`document_id_FK`,`officer_id_FK`) values 
(1,'uploaded','DEE JAY CRISTOBAL','Uploaded hello test certificate','2026-07-27 10:53:10.449384',1,30),
(2,'uploaded','DEE JAY CRISTOBAL','Uploaded QWEZXCRT','2026-07-27 11:04:12.145989',2,30),
(3,'uploaded','DEE JAY CRISTOBAL','Uploaded cxz','2026-07-27 11:06:17.079798',3,30),
(4,'uploaded','DEE JAY CRISTOBAL','Uploaded kjkl','2026-07-27 11:16:30.414755',4,30),
(5,'uploaded','DEE JAY CRISTOBAL','Uploaded rrrrrrr','2026-07-27 11:20:11.938683',5,30);

/*Table structure for table `document_pin` */

DROP TABLE IF EXISTS `document_pin`;

CREATE TABLE `document_pin` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `pinned_at` datetime(6) NOT NULL,
  `document_id_FK` int(11) NOT NULL,
  `officer_id_FK` int(11) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `DOCUMENT_PIN_document_id_FK_officer_id_FK_776da9b1_uniq` (`document_id_FK`,`officer_id_FK`),
  KEY `DOCUMENT_PIN_officer_id_FK_36d52f31_fk_OFFICER_USER_user_id_PK` (`officer_id_FK`),
  CONSTRAINT `DOCUMENT_PIN_document_id_FK_9577c92e_fk_DOCUMENT_document_id_PK` FOREIGN KEY (`document_id_FK`) REFERENCES `document` (`document_id_PK`),
  CONSTRAINT `DOCUMENT_PIN_officer_id_FK_36d52f31_fk_OFFICER_USER_user_id_PK` FOREIGN KEY (`officer_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `document_pin` */

/*Table structure for table `event` */

DROP TABLE IF EXISTS `event`;

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
  KEY `EVENT_created_by_user_id_FK_ace80cb6_fk_OFFICER_USER_user_id_PK` (`created_by_user_id_FK`),
  CONSTRAINT `EVENT_created_by_user_id_FK_ace80cb6_fk_OFFICER_USER_user_id_PK` FOREIGN KEY (`created_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=18 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `event` */

insert  into `event`(`event_id_PK`,`title`,`description`,`venue`,`event_date`,`event_time`,`end_time`,`event_type`,`status`,`attendance_open`,`attendance_closed`,`quorum_required`,`quorum_reached`,`created_at`,`updated_at`,`created_by_user_id_FK`,`auto_generate_certificates`,`certificate_issue_date`,`certificate_prefix`,`given_place`) values 
(1,'ISU OPENING CEREMONY','Test on 7/27/2026','Research Minante 1','2026-07-27','18:30:00.000000','19:00:00.000000','Monthly Meeting','Completed',0,1,60,0,'2026-07-27 09:28:06.049773','2026-07-27 11:24:54.037874',30,1,'2026-07-27','ISUCauFA-123','ISU CAUAYAN'),
(2,'GABI NG LAGIM','KMJS!','MINANTE 1 RESEARCH','2026-07-27','20:13:00.000000','20:20:00.000000','Workshop','Completed',0,1,60,0,'2026-07-27 12:10:24.812267','2026-07-27 12:44:20.720013',44,1,'2026-07-27','ISUCauFA-VON','CCSICT'),
(3,'ML TOURNAMENT','5V5 NS VS WMAD','AMPITHEATER','2026-07-28','17:30:00.000000','17:35:00.000000','Monthly Meeting','Completed',0,1,60,0,'2026-07-28 09:27:02.342704','2026-07-28 13:56:25.611111',44,1,'2026-07-28','ISUCauFA-III','RESEARCH ANNEX'),
(4,'SCHOLARSHIP','BRIEFING MEETING!','ALICIA','2026-07-28','18:30:00.000000',NULL,'hahaha','Completed',0,1,60,0,'2026-07-28 10:27:06.768912','2026-07-28 14:01:36.642394',44,1,'2026-07-28','ISUCauFA-COL','AUDITORIUM ALICIA'),
(5,'LEAGUE OF LEGENDS','5V5 NILA NI FAKER','ISU ECHAGUE','2026-07-28','18:30:00.000000',NULL,'QWERTYzxc','Completed',0,1,60,0,'2026-07-28 10:30:49.255378','2026-07-28 13:54:17.556447',44,1,'2026-07-28','ISUCauFA-ZXC','SOUTH KOREA'),
(6,'zxczxczxc','SGFSGHGHGH','GAGOOO','2026-07-28','18:35:00.000000',NULL,'zxc123','Completed',0,1,60,0,'2026-07-28 10:35:02.918515','2026-07-28 14:01:44.582166',44,1,'2026-07-28','ISUCauFA-FFF','CAUAYAN'),
(7,'zzzzzzzz','zxxxxxxxxx','xcccccccccc','2026-07-28','18:40:00.000000',NULL,'Otherss','Completed',0,1,60,0,'2026-07-28 10:39:50.124075','2026-07-28 14:01:40.674288',44,1,'2026-07-28','ISUCauFA-ATTCV','bbbb'),
(8,'vvv','xcxcvxcv','xcvxxcv','2026-07-28','18:53:00.000000',NULL,'Otherss','Completed',0,1,60,0,'2026-07-28 10:54:10.709908','2026-07-28 13:56:31.621326',44,1,'2026-07-28','ISUCauFA-ATTQWE','hhhh'),
(9,'kkkkkkkkk','llllllllll','ljjjjjjjjjj','2026-07-28','19:19:00.000000',NULL,'Seminar','Completed',0,1,60,0,'2026-07-28 11:20:07.231278','2026-07-28 11:20:28.929693',44,1,'2026-07-28','ISUCauFA-hhATT','hhhhhhhh'),
(10,'aaaaaaaa','bbbbbbbbbbb','cccccccc','2026-07-28','19:32:00.000000',NULL,'Otherss','Completed',0,1,60,0,'2026-07-28 11:32:50.529416','2026-07-28 13:56:42.890750',44,1,'2026-07-28','ISUCauFA-ATTERT','ffffff'),
(11,'CCC','CCCC','CCCCCCCC','2026-07-28','19:33:00.000000',NULL,'General Assembly','Completed',0,1,60,0,'2026-07-28 11:34:06.580301','2026-07-28 14:01:56.271939',44,1,'2026-07-28','ISUCauFA-ATTC','CCCC'),
(12,'fghjn','dhgsfha','agfhagha','2026-07-28','20:01:00.000000',NULL,'General Assembly','Completed',0,1,60,0,'2026-07-28 12:01:44.915278','2026-07-28 12:02:01.508499',44,1,'2026-07-28','ISUCauFA-ATT','aghagh'),
(13,'dddd','dddddddddd','ddddddddddd','2026-07-28','21:38:00.000000',NULL,'General Assembly','Completed',0,1,60,0,'2026-07-28 13:38:32.760503','2026-07-28 13:39:24.898182',44,1,'2026-07-30','ISUCauFA-ATTERT','asdasdasd'),
(14,'ttt','tttttt','ttt','2026-07-28','21:41:00.000000',NULL,'QWERTYzxc','Completed',0,1,60,0,'2026-07-28 13:41:41.248922','2026-07-28 13:45:25.737534',44,1,'2026-07-28','ISUCauFA-ATT','yyyyyyyy'),
(15,'crtyrty','wrywtywu','uwtuwtruwrtubwub','2026-07-28','21:44:00.000000',NULL,'General Assembly','Completed',0,1,60,0,'2026-07-28 13:45:06.522107','2026-07-28 13:48:53.508651',44,1,'2026-07-28','ISUCauFA-ATT','wb  tuw ubwuw'),
(16,'jjjj','jjjj','jjjjj','2026-07-28','21:49:00.000000',NULL,'General Assembly','Completed',0,1,60,0,'2026-07-28 13:49:19.459396','2026-07-28 14:14:41.273810',44,1,'2026-07-28','ISUCauFA-ATTjjjj','jjjj'),
(17,'final?>','final?>','final?>','2026-07-28','22:14:00.000000',NULL,'General Assembly','Completed',0,1,60,0,'2026-07-28 14:15:04.914784','2026-07-28 14:15:27.638936',44,1,'2026-07-28','ISUCauFA-ATTfinal?>','final?>');

/*Table structure for table `event_type` */

DROP TABLE IF EXISTS `event_type`;

CREATE TABLE `event_type` (
  `event_type_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`event_type_id_PK`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `event_type` */

insert  into `event_type`(`event_type_id_PK`,`name`,`created_at`) values 
(1,'General Assembly','2026-07-28 10:09:49.929457'),
(2,'Monthly Meetings','2026-07-28 10:09:49.938002'),
(3,'Seminar','2026-07-28 10:09:49.945190'),
(4,'Workshop','2026-07-28 10:09:49.954756'),
(5,'Otherss','2026-07-28 10:09:49.965328'),
(6,'QWERTYzxc','2026-07-28 10:17:50.569500'),
(7,'zxc','2026-07-28 10:22:54.687983'),
(8,'zxc123','2026-07-28 10:25:08.745893'),
(9,'hahaha','2026-07-28 10:26:14.478386');

/*Table structure for table `financial_document_archive` */

DROP TABLE IF EXISTS `financial_document_archive`;

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
  KEY `FINANCIAL_DOCUMENT_A_uploaded_by_user_id__2e803a5e_fk_OFFICER_U` (`uploaded_by_user_id_FK`),
  CONSTRAINT `FINANCIAL_DOCUMENT_A_uploaded_by_user_id__2e803a5e_fk_OFFICER_U` FOREIGN KEY (`uploaded_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `financial_document_archive` */

/*Table structure for table `fund_transaction` */

DROP TABLE IF EXISTS `fund_transaction`;

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
  KEY `FUND_TRANSA_directi_c179cb_idx` (`direction`),
  KEY `FUND_TRANSA_source__6023fe_idx` (`source_type`,`source_id`),
  CONSTRAINT `FUND_TRANSACTION_recorded_by_user_id__4d5f9ffd_fk_OFFICER_U` FOREIGN KEY (`recorded_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=15 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `fund_transaction` */

insert  into `fund_transaction`(`transaction_id_PK`,`direction`,`amount`,`source_type`,`source_id`,`description`,`reference_number`,`recorded_at`,`recorded_by_user_id_FK`) values 
(13,'inflow',100.00,'membership_fee',13,'JUSTIN VON T VERGARA — Membership Fee (registration)','REG-20260727115050-142joe','2026-07-27 11:54:00.900458',41),
(14,'inflow',100.00,'membership_fee',14,'TRISTAN R ILLARDE — Membership Fee (registration)','REG-20260727120209-142joe2','2026-07-27 12:03:49.269218',41);

/*Table structure for table `global_audit_trail` */

DROP TABLE IF EXISTS `global_audit_trail`;

CREATE TABLE `global_audit_trail` (
  `trail_id` int(11) NOT NULL AUTO_INCREMENT,
  `table_name` varchar(100) NOT NULL,
  `record_id` int(11) NOT NULL,
  `action` varchar(50) NOT NULL,
  `old_values` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`old_values`)),
  `new_values` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`new_values`)),
  `actor_type` varchar(50) NOT NULL,
  `actor_id` int(11) DEFAULT NULL,
  `actor_name` varchar(255) NOT NULL,
  `ip_address` char(39) DEFAULT NULL,
  `device_info` varchar(255) DEFAULT NULL,
  `notes` longtext DEFAULT NULL,
  `timestamp` datetime(6) NOT NULL,
  `document_archive_id_FK` int(11) DEFAULT NULL,
  `entry_hash` varchar(64) DEFAULT NULL,
  `hmac_signature` varchar(64) DEFAULT NULL,
  `previous_hash` varchar(64) DEFAULT NULL,
  PRIMARY KEY (`trail_id`),
  KEY `GLOBAL_AUDI_table_n_f2953e_idx` (`table_name`,`record_id`,`timestamp`),
  KEY `GLOBAL_AUDIT_TRAIL_document_archive_id__cd699f95_fk_FINANCIAL` (`document_archive_id_FK`),
  CONSTRAINT `GLOBAL_AUDIT_TRAIL_document_archive_id__cd699f95_fk_FINANCIAL` FOREIGN KEY (`document_archive_id_FK`) REFERENCES `financial_document_archive` (`document_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=325 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `global_audit_trail` */

insert  into `global_audit_trail`(`trail_id`,`table_name`,`record_id`,`action`,`old_values`,`new_values`,`actor_type`,`actor_id`,`actor_name`,`ip_address`,`device_info`,`notes`,`timestamp`,`document_archive_id_FK`,`entry_hash`,`hmac_signature`,`previous_hash`) values 
(1,'officer_user',24,'CREATED',NULL,'{\"id\": \"24\", \"full_name\": \"JASMINE ROTUGAL\", \"username\": \"treasurer\", \"email\": \"jasmine.rotugal_cyn@isu.edu.ph\", \"role\": \"Treasurer\", \"account_status\": \"Active\", \"term_start\": \"2026-07-25\", \"term_end\": \"2026-12-31\", \"department_id\": null, \"department_name\": null, \"department_code\": null, \"mfa_enabled\": \"False\", \"created_at\": \"2026-07-25T10:21:16.943123+00:00\", \"updated_at\": \"2026-07-25T10:21:16.943123+00:00\"}','President',23,'President Account','112.202.47.68',NULL,'Created officer account for JASMINE ROTUGAL','2026-07-25 10:21:16.950440',NULL,'15e785787426a241b3ac43568ee43b7e91f165d7f8be9f57e059935fa57988fa','0f0e1d8b30f3f287b8ee5e830cc617b622649f252291da54b03c760659c4fad6','0000000000000000000000000000000000000000000000000000000000000000'),
(2,'officer_user',25,'CREATED',NULL,'{\"id\": \"25\", \"full_name\": \"FREDERICK MADAYAG\", \"username\": \"auditor\", \"email\": \"manchoco69@gmail.com\", \"role\": \"Auditor\", \"account_status\": \"Active\", \"term_start\": \"2026-12-05\", \"term_end\": \"2026-12-31\", \"department_id\": null, \"department_name\": null, \"department_code\": null, \"mfa_enabled\": \"False\", \"created_at\": \"2026-07-25T10:22:01.950602+00:00\", \"updated_at\": \"2026-07-25T10:22:01.950602+00:00\"}','President',23,'President Account','112.202.47.68',NULL,'Created officer account for FREDERICK MADAYAG','2026-07-25 10:22:01.956729',NULL,'4600df6aead8e5ec72cd772428f39e6fa442c69a80e46259f17e7dbb21f85aa5','0ac069c51b49cf65828d9774b0c7b08c57ee430d4fa5a82519f8de215fc25cd9','15e785787426a241b3ac43568ee43b7e91f165d7f8be9f57e059935fa57988fa'),
(3,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','2405:8d40:4c19:b784:d6c:b1ce:53a1:3847','Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (0 records)','2026-07-25 10:23:08.700395',NULL,'cb8c4fc32d6794dc7ef839ed5937aafb00416625f93dfb13ae54810f65286758','ed4600807b6b4006a6b7b75b3337eea9ec286a54f2a318d8a82e609459e6742e','4600df6aead8e5ec72cd772428f39e6fa442c69a80e46259f17e7dbb21f85aa5'),
(4,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','2405:8d40:4c19:b784:d6c:b1ce:53a1:3847','Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-25 10:23:08.782653',NULL,'bedb7932d568e2ad5411651399549938fd1c3d29697d56c2e976204484e38965','f22f380330097434b4f3ef469515939c3d4a743f22b0b3859db7f3967ae778d0','cb8c4fc32d6794dc7ef839ed5937aafb00416625f93dfb13ae54810f65286758'),
(5,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (0 records)','2026-07-25 10:24:32.785888',NULL,'068154dc0ce00a2ce9073d58188445300e495723c841c8fc46be8069d2e3995f','3e80f60af96066b5660b45e6e0b79eda8658d331953dcb1f9d1c04720d1472f6','bedb7932d568e2ad5411651399549938fd1c3d29697d56c2e976204484e38965'),
(6,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-25 10:24:32.799579',NULL,'577735e22ffab522971a6ed03f06164e51d49ab77e5c41c2203424cbf5565f6a','d576fe8d02fc31021e636d2a0b1fb7170c5a7c0be3117a169345ed9729180b83','0000000000000000000000000000000000000000000000000000000000000000'),
(7,'bylaws_documents',0,'READ',NULL,NULL,'President',23,'President Account','112.198.120.53',NULL,'Listed bylaws document archive','2026-07-25 10:26:43.814453',NULL,'90f797c31f1aee3f792aa4dd260df1cd494451c926eedc85532a031f02b64e73','aba48d50d28e35371c6a1a84613c58915f02c9f5a8bc3d8f8a161a2f11cf73f4','577735e22ffab522971a6ed03f06164e51d49ab77e5c41c2203424cbf5565f6a'),
(8,'policy_constants',0,'READ',NULL,NULL,'President',23,'President Account','112.198.120.53',NULL,'Retrieved policy constants snapshot','2026-07-25 10:26:43.846297',NULL,'bc77a4c91a628fc0862e815eb847577421fad526e0dbb3484d7a2d2c1a6f05be','e17371b51a1fc7df2cfbb9e8653507dc1021996be5c1ad0cd3f69d6063f6a0e9','90f797c31f1aee3f792aa4dd260df1cd494451c926eedc85532a031f02b64e73'),
(9,'officer_user',25,'UPDATED',NULL,'{\"id\": \"25\", \"full_name\": \"FREDERICK MADAYAG\", \"username\": \"auditor\", \"email\": \"manchoco69@gmail.com\", \"role\": \"Auditor\", \"account_status\": \"Active\", \"term_start\": \"2026-07-01\", \"term_end\": \"2026-08-01\", \"department_id\": null, \"department_name\": null, \"department_code\": null, \"mfa_enabled\": \"False\", \"created_at\": \"2026-07-25T10:22:01.950602+00:00\", \"updated_at\": \"2026-07-25T10:27:54.035499+00:00\"}','President',23,'President Account','112.198.120.53',NULL,'Updated officer account for FREDERICK MADAYAG','2026-07-25 10:27:54.044310',NULL,'35196ecabca4fbd5f6d91798952bbb3381b9eceb1a8461712295c81c9a326066','a3581b4b5395cf5e1b995c99316e21293cf93d5261fca915e2ae99715ad27225','bc77a4c91a628fc0862e815eb847577421fad526e0dbb3484d7a2d2c1a6f05be'),
(10,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','Treasurer viewed medical aid list (0 records)','2026-07-25 10:39:44.030251',NULL,'25664ae8b2ecf23fbdc190c6122f92d26bc95d58967568bfdc1e0142570c25fa','812d4ad16bd944d5c8e9b5b020c5e762fb7d36fbc237add2f4a3e7609cd8b636','35196ecabca4fbd5f6d91798952bbb3381b9eceb1a8461712295c81c9a326066'),
(11,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','Treasurer viewed returned medical aid list (0 records)','2026-07-25 10:39:44.097537',NULL,'83bc7c47d7dfccf162bd7f2a2f8a08d4f9d893ad3920f3aa3e93947fe1cccfb7','fc5e973c15beccfe712032fbb8687f5d11c1c640be8197894c8507782117a9c8','25664ae8b2ecf23fbdc190c6122f92d26bc95d58967568bfdc1e0142570c25fa'),
(12,'member_registration_request',1,'TREASURER_VERIFIED',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','112.198.120.53',NULL,'Treasurer verified registration request for Fred G Mendoza','2026-07-25 10:40:06.156935',NULL,'00e92292a3eb2fc682431b359d8d7cfdf3e98ce6ee3a40ff4bf083234b477be8','1d600a63da33654570951302f47ed0576e9edf7cdfdae275302c8834afd92fde','83bc7c47d7dfccf162bd7f2a2f8a08d4f9d893ad3920f3aa3e93947fe1cccfb7'),
(13,'member_registration_request',1,'AUDITOR_VERIFIED',NULL,NULL,'Auditor',25,'FREDERICK MADAYAG','112.198.120.53',NULL,'Auditor verified registration request for Fred G Mendoza','2026-07-25 10:41:08.740193',NULL,'c13c75b500b9b90d30d54d3b7eb61fe3de0245d8e9be0d986e47cfcd7f716681','ac8940282d996725d586dbe7667ddb6c4cdf2a741d00f42abfeb681fb7db236f','00e92292a3eb2fc682431b359d8d7cfdf3e98ce6ee3a40ff4bf083234b477be8'),
(14,'officer_user',23,'UPDATED',NULL,'{\"id\": \"23\", \"full_name\": \"President Account\", \"username\": \"president\", \"email\": \"vergarajustin636@gmail.com\", \"role\": \"President\", \"account_status\": \"Active\", \"term_start\": null, \"term_end\": null, \"department_id\": null, \"department_name\": null, \"department_code\": null, \"mfa_enabled\": \"True\", \"created_at\": \"2026-07-25T10:20:09.274412+00:00\", \"updated_at\": \"2026-07-25T10:43:26.571920+00:00\"}','President',23,'President Account','112.202.47.68',NULL,'Updated officer account for President Account','2026-07-25 10:43:26.578174',NULL,'5ccc3bd4059b950fa06a69ce2fef18d21d9279eb926b2d5dd41ca6ce6dad2c2c','4e3df168a2bb04ddd4660dbfe0216da4628f6241e856bcdd23be7ce489b11ce4','c13c75b500b9b90d30d54d3b7eb61fe3de0245d8e9be0d986e47cfcd7f716681'),
(15,'member_registration_request',1,'PRESIDENT_APPROVED',NULL,'{\"member_id\": \"1\", \"officer_user_id\": \"26\", \"fee_id\": \"1\", \"status\": \"President Approved\"}','President',23,'President Account','112.202.47.68',NULL,'President approved registration for Fred G Mendoza. Member/OfficerUser/MembershipFee created.','2026-07-25 10:43:50.569269',NULL,'bbb23badb8bc03ed2b6b1eb29dfad2e924c9ccec177538198ae1516106d17e81','544495b57552b3ba84428f43e7aaa1799f0fd6bbf1a413e5494c2062aa2f530d','5ccc3bd4059b950fa06a69ce2fef18d21d9279eb926b2d5dd41ca6ce6dad2c2c'),
(16,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','2405:8d40:4c19:b784:d6c:b1ce:53a1:3847','Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-25 10:45:56.278418',NULL,'8ed1962b66b65f1a4f33e41d0bbe98d592eefcc7341741a54fcaec1c7c33b277','1a0afafa80409b704af5d4895813898cff20a7b278f0285c5693a956d282e9d4','bbb23badb8bc03ed2b6b1eb29dfad2e924c9ccec177538198ae1516106d17e81'),
(17,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','2405:8d40:4c19:b784:d6c:b1ce:53a1:3847','Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (0 records)','2026-07-25 10:45:56.287327',NULL,'3c60282c856615dd5140512f919fd3bbc3e6b0fc3f87e731b36bb68c45b9f237','2b8bf73c27c7cdb3ec2ddbd07687f864142ced08bc4fafb461a9cc377982e40d','0000000000000000000000000000000000000000000000000000000000000000'),
(18,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (0 records)','2026-07-25 10:46:51.334833',NULL,'836a10230dec230dc7e2ffa2c826d7416e51ff362e1d01bfa41308c94f27eeba','8eac36695750c3541e505d0369541c1b6bedb5a03aeecbee115b533a0c59234b','3c60282c856615dd5140512f919fd3bbc3e6b0fc3f87e731b36bb68c45b9f237'),
(19,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-25 10:46:51.542267',NULL,'a18356bc93885fe15f2238ec00b9b2a6545da7e07eb399729d72313d32fe05dc','2f4e2b8eb0b8e6a671d258e2435e1a18daa88370e3d5601da84d42943d7ce4f2','836a10230dec230dc7e2ffa2c826d7416e51ff362e1d01bfa41308c94f27eeba'),
(20,'member_registration_request',2,'TREASURER_VERIFIED',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','212.102.51.117',NULL,'Treasurer verified registration request for Jasmine Rotugal','2026-07-25 10:47:23.441455',NULL,'e0828a3191ece3e944736d20eef5e6fc5393ac5ba5a6d5966265092bac68f96d','514e4beaedbaf43bc4bfbf4a45371f0e577143368f7adbc50ed92f5dfdce0dfe','a18356bc93885fe15f2238ec00b9b2a6545da7e07eb399729d72313d32fe05dc'),
(21,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-25 10:48:36.867086',NULL,'dd26bdd6655fd0173de0aa8a600083a0585cf9013ad561f5c051364a86913b9d','c6618b87c320ae43b5c08b433465f45d04a8fbf0112277725159482ac3e277d3','e0828a3191ece3e944736d20eef5e6fc5393ac5ba5a6d5966265092bac68f96d'),
(22,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (0 records)','2026-07-25 10:48:36.870612',NULL,'7983b60730fd551eaf9afc2b1fff7b9909920581ff75e278bea03fefbeb49682','b9b33271848c4b8b2aa8abc95467441f48b24b4e7ebde300c34cff481a9b0544','e0828a3191ece3e944736d20eef5e6fc5393ac5ba5a6d5966265092bac68f96d'),
(23,'member_registration_request',3,'TREASURER_VERIFIED',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','212.102.51.117',NULL,'Treasurer verified registration request for JUSTIN VON T VERGARA','2026-07-25 10:48:45.150318',NULL,'1ba39aa3739607ff6a35bdfcf7b11416621c9effe098ba246174b639522740e8','ed09c16dd1f006da7052896e97f05fadf216c0ad8874125165558e96a4009f25','7983b60730fd551eaf9afc2b1fff7b9909920581ff75e278bea03fefbeb49682'),
(24,'member_registration_request',3,'AUDITOR_VERIFIED',NULL,NULL,'Auditor',25,'FREDERICK MADAYAG','112.198.120.53',NULL,'Auditor verified registration request for JUSTIN VON T VERGARA','2026-07-25 10:49:50.340527',NULL,'b510b767bd43572d4bf3f7fd22bcb4274d80db6a51aa26aacc2aeee05df2ceea','0dce62b5e7a7be183417f9232d93777e1292b40c5beac995b9e5a1e88425cb5c','1ba39aa3739607ff6a35bdfcf7b11416621c9effe098ba246174b639522740e8'),
(25,'member_registration_request',2,'AUDITOR_VERIFIED',NULL,NULL,'Auditor',25,'FREDERICK MADAYAG','112.198.120.53',NULL,'Auditor verified registration request for Jasmine Rotugal','2026-07-25 10:50:04.517489',NULL,'8fdea6c2a1dd761f0844ccaf65e8f23e031a11ab1f3cddbb0b7b7f4be5ff10ca','03173d9927fdd27c33e8d0f26fac72e13dc55a0c1d24f721f3b5ed56e18243a3','b510b767bd43572d4bf3f7fd22bcb4274d80db6a51aa26aacc2aeee05df2ceea'),
(26,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','2405:8d40:4c19:b784:d6c:b1ce:53a1:3847','Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (0 records)','2026-07-25 10:50:20.061522',NULL,'f121d476cb81f85d5340d22bb02bb4d1f055c989113d58d8c4299663cfb6497b','d66dda5d3705844c5ea9936f27dc2b9e14d54aaca36550adc0d0b8a6d5753081','8fdea6c2a1dd761f0844ccaf65e8f23e031a11ab1f3cddbb0b7b7f4be5ff10ca'),
(27,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','2405:8d40:4c19:b784:d6c:b1ce:53a1:3847','Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-25 10:50:20.191632',NULL,'6082afb18f8978ae35f692e08d295fc4d47f3f9cc42736d0f17407d3d20bd4e6','b96a1f75fb81987bc561513a542cf0795490c7ebb31da47a726ab3631a408752','f121d476cb81f85d5340d22bb02bb4d1f055c989113d58d8c4299663cfb6497b'),
(28,'member_registration_request',3,'PRESIDENT_APPROVED',NULL,'{\"member_id\": \"2\", \"officer_user_id\": \"27\", \"fee_id\": \"2\", \"status\": \"President Approved\"}','President',23,'President Account','112.202.47.68',NULL,'President approved registration for JUSTIN VON T VERGARA. Member/OfficerUser/MembershipFee created.','2026-07-25 10:50:48.694778',NULL,'9665a35ee7261db8c7db8dac017d301dd83211e7c4643d41806ade71e33c6667','ff9dd1789924a11c2046e6b2b3ae51783f253292d7d07f5ca506def7eafc2eb7','6082afb18f8978ae35f692e08d295fc4d47f3f9cc42736d0f17407d3d20bd4e6'),
(29,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','2405:8d40:4c19:b784:d6c:b1ce:53a1:3847','Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (0 records)','2026-07-25 10:51:01.522938',NULL,'27d2aff86fd941f891be95dfe1e286356edb7e639b284316520bd1dd1407cbb4','44a5bc3a83f71a3f6a77bf6c01f3e3ff76d5300b24fa70bec7c0e6cf18f15641','9665a35ee7261db8c7db8dac017d301dd83211e7c4643d41806ade71e33c6667'),
(30,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','2405:8d40:4c19:b784:d6c:b1ce:53a1:3847','Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-25 10:51:01.634151',NULL,'c4052b7fc7864cb04d70b7e5ec03de8f071eb598872fe2a789976f810d49c544','4765d9b4c427895b88a82b370a1f3e1f4c6e4fefbd8fd4aa0b9a5cd8279e5166','27d2aff86fd941f891be95dfe1e286356edb7e639b284316520bd1dd1407cbb4'),
(31,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','2405:8d40:4c19:b784:d6c:b1ce:53a1:3847','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Treasurer viewed medical aid list (0 records)','2026-07-25 10:51:07.893881',NULL,'217b26d8cceca23919f5fcfc36b88444c6ac49e7bea4baf8e854711120a82da3','d86a20dffee67ac439fa739ea8bd431f51aff42a7607a6ac2aa85ea919249ce3','c4052b7fc7864cb04d70b7e5ec03de8f071eb598872fe2a789976f810d49c544'),
(32,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','2405:8d40:4c19:b784:d6c:b1ce:53a1:3847','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-25 10:51:07.968700',NULL,'b43a7120059b43eccc81f38d4948fce9b1b1a6d6b96df9c921817070b2b95091','ac91ffee407c6717c6090e110e06f2b8f47240b9cb2ba75c6bf7d5e15aa0a924','217b26d8cceca23919f5fcfc36b88444c6ac49e7bea4baf8e854711120a82da3'),
(33,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','2405:8d40:4c19:b784:d6c:b1ce:53a1:3847','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Treasurer viewed medical aid list (0 records)','2026-07-25 10:51:18.788911',NULL,'92dd65b66e6237161b2ec422f4a73e2c60a4ff5aad8d2ce9386ff5f868d5b985','c4b43c0c66d4ed68adb258e77c67ff0f7c7be75ca4664d84ee5ac5781494109b','b43a7120059b43eccc81f38d4948fce9b1b1a6d6b96df9c921817070b2b95091'),
(34,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','2405:8d40:4c19:b784:d6c:b1ce:53a1:3847','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-25 10:51:18.902516',NULL,'830f0bce8f79c9f7ec733484cc51590077dda74c781e0cb491723bc4de587576','b622e3c54d3bc46bcc932ee2a1242474457ba51f7cddd8a628e114003370e22e','92dd65b66e6237161b2ec422f4a73e2c60a4ff5aad8d2ce9386ff5f868d5b985'),
(35,'member_registration_request',2,'PRESIDENT_APPROVED',NULL,'{\"member_id\": \"3\", \"officer_user_id\": \"28\", \"fee_id\": \"3\", \"status\": \"President Approved\"}','President',23,'President Account','112.202.47.68',NULL,'President approved registration for Jasmine Rotugal. Member/OfficerUser/MembershipFee created.','2026-07-25 10:51:57.639823',NULL,'cccab84c364455613b32f826bb645cc59ef14750e9b0d2e58d65a23ad021f6e5','a49e243811b00203379c3934b974be7c0962904e383259cea9e361e44078de7b','830f0bce8f79c9f7ec733484cc51590077dda74c781e0cb491723bc4de587576'),
(36,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-25 10:53:03.462109',NULL,'76b75f8f091ec2ecf88c0f55c3a6515b9b57ea7022a75fa9fe057a9e74341f31','02b8508c1d31aef4fef17d235b160c5f52f3c1ec3a6509647ac18195ce58c8f4','cccab84c364455613b32f826bb645cc59ef14750e9b0d2e58d65a23ad021f6e5'),
(37,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (0 records)','2026-07-25 10:53:03.530230',NULL,'ee5e1a8a3fc456ab3c8dbdf0a113886cf4582a91a4facf8b55b0e51fb87aa0ab','62e591ec67f88ea499b3982fe4214195bd369068918c58b4f0fe052642995c7a','76b75f8f091ec2ecf88c0f55c3a6515b9b57ea7022a75fa9fe057a9e74341f31'),
(38,'member_registration_request',4,'TREASURER_VERIFIED',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','212.102.51.117',NULL,'Treasurer verified registration request for Frederick H Zamboanga','2026-07-25 10:53:17.408231',NULL,'82503901dda4c8378b31007b670f1a5cbe0c39ee463e96652f2be16537b49ce6','fd7ce58d77549dfb1529b94a5c37e2ada5faaa5522e271f6a99b959ebdc90194','ee5e1a8a3fc456ab3c8dbdf0a113886cf4582a91a4facf8b55b0e51fb87aa0ab'),
(39,'member_registration_request',4,'AUDITOR_VERIFIED',NULL,NULL,'Auditor',25,'FREDERICK MADAYAG','112.198.120.53',NULL,'Auditor verified registration request for Frederick H Zamboanga','2026-07-25 10:53:35.156441',NULL,'e680428b5bd1077cb3fb0c9c7dd7604eba2f9ef6d2edc1b4e23d24a2c3ed9dd1','e5a5ddb29fd911ef96b5f8f8e1135506ee8b76541b7c922475ce6b1e90feb126','82503901dda4c8378b31007b670f1a5cbe0c39ee463e96652f2be16537b49ce6'),
(40,'member_registration_request',4,'PRESIDENT_APPROVED',NULL,'{\"member_id\": \"4\", \"officer_user_id\": \"29\", \"fee_id\": \"4\", \"status\": \"President Approved\"}','President',23,'President Account','112.202.47.68',NULL,'President approved registration for Frederick H Zamboanga. Member/OfficerUser/MembershipFee created.','2026-07-25 10:53:52.516849',NULL,'3a47c963eb2cab83c56232447471183838666729cce8f65626834bbd284445d7','9bed8a8830afdcbfa2a6312370dbbb4ef07f8f4c058bf82e8ad539f16c415717','e680428b5bd1077cb3fb0c9c7dd7604eba2f9ef6d2edc1b4e23d24a2c3ed9dd1'),
(41,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','2405:8d40:4c19:b784:d6c:b1ce:53a1:3847','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Treasurer viewed medical aid list (0 records)','2026-07-25 10:54:34.223616',NULL,'33c204856e5dee94734d2d00be9b695d8ae56b8e780b167ce16a6d59f4412c34','51a5cd1a5407143a35a716e31e9267327ff3c099d94b9abde9b16bf146cf69ed','3a47c963eb2cab83c56232447471183838666729cce8f65626834bbd284445d7'),
(42,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','2405:8d40:4c19:b784:d6c:b1ce:53a1:3847','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-25 10:54:34.333956',NULL,'aaaa408850d55fc32f77eb6b0767d9cc8c204a979f537a8aea5c84734cbca036','1cfa52bdf2079afc99a4d58b88d29fd62932883c90f199f91a4e8770ecb44810','33c204856e5dee94734d2d00be9b695d8ae56b8e780b167ce16a6d59f4412c34'),
(43,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','2405:8d40:4c19:b784:d6c:b1ce:53a1:3847','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Treasurer viewed medical aid list (0 records)','2026-07-25 10:56:08.831955',NULL,'c4472f8087c7a3ed0e2d86cade343d9120c0659557bcb47e99ced3526528fdd0','8f8e5c08dec375cb5ce014834a0e73e0bb33a1a609cbee7b660c3f4b941fe190','aaaa408850d55fc32f77eb6b0767d9cc8c204a979f537a8aea5c84734cbca036'),
(44,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','2405:8d40:4c19:b784:d6c:b1ce:53a1:3847','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-25 10:56:08.960840',NULL,'886e81d67bb88ac8b71103946c66ad9d0f97bc5cb343361afccc8eaa10d7ed88','393a7d9fd37f2ec737b5fd778f3590192029582c67ace7c752b3bffd7e12c427','c4472f8087c7a3ed0e2d86cade343d9120c0659557bcb47e99ced3526528fdd0'),
(45,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','2405:8d40:4c19:b784:d6c:b1ce:53a1:3847','Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-25 10:56:33.525317',NULL,'cfb701f504804b34080a58d1b9e367b48bad017d7db9454b6d8a543c6c8f6028','b3f8c3b5c2435a494ae2f8f327f9ff6aaf8b913b1f0d659e88c5c87112d0d823','886e81d67bb88ac8b71103946c66ad9d0f97bc5cb343361afccc8eaa10d7ed88'),
(46,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','2405:8d40:4c19:b784:d6c:b1ce:53a1:3847','Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (0 records)','2026-07-25 10:56:33.598211',NULL,'9fb9aa547e020e0d92c7328916176460d05392e0e3bde1ad1382a7f42ffa8df0','71b16e5149cd7da4dbb8e12d76f1a0cfc993b3a5b0f259582122257e230b3dd6','cfb701f504804b34080a58d1b9e367b48bad017d7db9454b6d8a543c6c8f6028'),
(47,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','Treasurer viewed returned medical aid list (0 records)','2026-07-25 11:09:56.098266',NULL,'4fc0a3c0f6cb196e6aebfaacda324339eb279bc65dd131e78b81cee22173e03b','8022f88968efb91c2fc697681fff9c356d37c5347c0fdd27f3708b645d8ecf0a','9fb9aa547e020e0d92c7328916176460d05392e0e3bde1ad1382a7f42ffa8df0'),
(48,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','Treasurer viewed medical aid list (0 records)','2026-07-25 11:09:56.160289',NULL,'7a2d48d6647e61e970c91c788eb95e7362a8c11c107a640cb65f473411fec053','2333b02522a7775fdc32de3d488c162aec1f38f20e58fc46774650c402dbc63b','4fc0a3c0f6cb196e6aebfaacda324339eb279bc65dd131e78b81cee22173e03b'),
(49,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-25 11:10:04.951224',NULL,'b4bbe9d4cf57dad2a35aaf6967a804dd93c08e85d1701944579e410d148ce7af','c2f7b24599705d55643afaf6e8da0ff2c73ee6630281d76a407f9ad9dde29876','7a2d48d6647e61e970c91c788eb95e7362a8c11c107a640cb65f473411fec053'),
(50,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (0 records)','2026-07-25 11:10:04.997886',NULL,'08289e89c99cbcd52875bcb32d0cd045abe056284e36d9e239ab3d27e3be8ae3','0c6161da2003cffd94c18e95784e27b637f1a3e673a2cbad944f063061b40a80','b4bbe9d4cf57dad2a35aaf6967a804dd93c08e85d1701944579e410d148ce7af'),
(51,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (0 records)','2026-07-25 11:11:48.209629',NULL,'b064d31db16e05ffa668ea232d525f90ab77d707ae320a506c59d27b63621f41','90afccd5ff230a4c7a9d0e45ab8ab0a1a2b62c0fd882a3e666b0935a19e30bfc','08289e89c99cbcd52875bcb32d0cd045abe056284e36d9e239ab3d27e3be8ae3'),
(52,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-25 11:11:48.271020',NULL,'cc27e396a6cf67af7b6fa6b6355e5fd8d49e353b03a83d688c401fcb0940e6c7','7eb34037b15bde6c4eb2082a6980c04d9310068b7534959ce11b83516c20a7ca','b064d31db16e05ffa668ea232d525f90ab77d707ae320a506c59d27b63621f41'),
(53,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','Treasurer viewed medical aid list (0 records)','2026-07-25 11:11:51.494286',NULL,'8d8bf7da190be77068240fe4fabdc95c4d49f743fa0a05636643738be17bd86d','45be504980dd8e27a41a8a746d30d281d31ff964c6ba7507d475ab0ead90a409','cc27e396a6cf67af7b6fa6b6355e5fd8d49e353b03a83d688c401fcb0940e6c7'),
(54,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','Treasurer viewed returned medical aid list (0 records)','2026-07-25 11:11:51.544014',NULL,'d59fd9489674fe0ffdc47117e13bfe0a9ccd22ed0a71b696922c15f5ef3aaab1','b48c7ebee855d48bb37bfe1fa74c8f8fcf703a4c97f8f61f12aa08acc58c6a16','8d8bf7da190be77068240fe4fabdc95c4d49f743fa0a05636643738be17bd86d'),
(55,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (1 records)','2026-07-25 11:19:43.684693',NULL,'901f8bd622abd3a172c8a7acc00ba054e39032b6ac6daecbb33eee4e5466fc6d','56cf35927ce226d91dd545cf2d0999e7770e6977c1c3edb77c30c118f5334bbb','d59fd9489674fe0ffdc47117e13bfe0a9ccd22ed0a71b696922c15f5ef3aaab1'),
(56,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-25 11:19:43.742960',NULL,'34bdc6b1224bbaec97af0edae597e27c27d6a97f0b54f0efc34ab2d997303dff','f7d2571080077db03b81ce78ccc5566ed3f6fe7aa2b566d0a65f7fa773c291e0','901f8bd622abd3a172c8a7acc00ba054e39032b6ac6daecbb33eee4e5466fc6d'),
(57,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','Treasurer viewed medical aid list (1 records)','2026-07-25 11:20:21.103014',NULL,'ac25c2f36b86ab6c9a3ddf48abeb8affd0fd1153f06bd0070c0b1666d6ffb687','2c4999f07b4bda0c85b2b75d49c7229552a15b827df079ac58e15bcae8d6c520','34bdc6b1224bbaec97af0edae597e27c27d6a97f0b54f0efc34ab2d997303dff'),
(58,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','Treasurer viewed returned medical aid list (0 records)','2026-07-25 11:20:21.256061',NULL,'9da4f54dccab73d6a978439e4ceef6c53fda1d74ae69204bb82a9fec2c7fb03b','f7784dd3eb1cbf4b8329155b6003573a959c1126e0ea1ace81a146b08fc056a8','ac25c2f36b86ab6c9a3ddf48abeb8affd0fd1153f06bd0070c0b1666d6ffb687'),
(59,'medical_aid',0,'READ',NULL,NULL,'Auditor',25,'FREDERICK MADAYAG','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','Auditor viewed pending medical aid list (1 records)','2026-07-25 11:21:31.300528',NULL,'9caf84a4d8a90fbef3924a34c0a97e579034eccf40560f859dbd5c15883ecb0b','72b047c31683aaf505da304e3483c579bd40e307fbd8f6b0e3fc357c65203906','9da4f54dccab73d6a978439e4ceef6c53fda1d74ae69204bb82a9fec2c7fb03b'),
(60,'medical_aid',1,'VERIFIED',NULL,NULL,'Auditor',25,'FREDERICK MADAYAG','112.198.120.53',NULL,'Reviewed by FREDERICK MADAYAG','2026-07-25 11:22:46.106543',NULL,'8fdcb38329da203a3e9cfe20fb3432abc41597e4fc1e6fd5bf11424f6b06f3e2','eb10e09194a29cab60e4df60ce432e6353aaa252dc9471fb00c9bff972ead9c9','9caf84a4d8a90fbef3924a34c0a97e579034eccf40560f859dbd5c15883ecb0b'),
(61,'death_aid',1,'VERIFIED',NULL,NULL,'Auditor',25,'FREDERICK MADAYAG','112.198.120.53',NULL,'Reviewed by FREDERICK MADAYAG','2026-07-25 11:22:46.106543',NULL,'b65e22c2466946076279103a1f3b8045e02f7e709a8c6df0232129c1443ed3ff','a132847f8e628958daf57299fec7241edd707fa5643fa7e1532bf0f7164c11af','8fdcb38329da203a3e9cfe20fb3432abc41597e4fc1e6fd5bf11424f6b06f3e2'),
(62,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (1 records)','2026-07-25 11:22:46.794189',NULL,'b8b4a02838038dc791836b33847a02edf5c8426b9d5f1a0422e0786035ac271a','e68fd99776da23d851983f929e274153de72eb94b89a14550d48b62ded5e4f49','b65e22c2466946076279103a1f3b8045e02f7e709a8c6df0232129c1443ed3ff'),
(63,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','Treasurer viewed medical aid list (1 records)','2026-07-25 11:31:41.824095',NULL,'7e5d1ed13e8e3e08a22e03564f527bc2c77dc35cb1a12b4d8920ac6a759d3ba1','06d84d58ff292951108d097b4da3fdc99b851682000a2aa2aa85ffbf080f6707','b8b4a02838038dc791836b33847a02edf5c8426b9d5f1a0422e0786035ac271a'),
(64,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','Treasurer viewed returned medical aid list (0 records)','2026-07-25 11:31:41.923121',NULL,'4344de25211749c9a2ab45c64ff44e9af6c11582e0651167d5d69075b65de306','82b535cb6b7ba9fecc8b196d071c9d92ce80d176d1eabe50f4925015b113cda4','7e5d1ed13e8e3e08a22e03564f527bc2c77dc35cb1a12b4d8920ac6a759d3ba1'),
(65,'monthly_dues',1,'CREATED',NULL,'{\"member\": \"Fred G Mendoza\", \"month_covered\": \"2026-03\", \"amount\": \"50.0\", \"payment_method\": \"Salary Deduction\", \"batch_ref\": \"ISUCauFA-26-1\"}','Treasurer',24,'JASMINE ROTUGAL','112.198.120.53',NULL,NULL,'2026-07-25 11:32:17.666399',NULL,'879d0f9c39bd3aab4aabadd48628e41ce9e222e28969d1a4e846d3bb07d13d02','380c87d2de88ced9d0865b15550a8cd90f384f49c5d3121d6fb6f8cfc3071a23','4344de25211749c9a2ab45c64ff44e9af6c11582e0651167d5d69075b65de306'),
(66,'monthly_dues',2,'CREATED',NULL,'{\"member\": \"JUSTIN VON T VERGARA\", \"month_covered\": \"2026-03\", \"amount\": \"50.0\", \"payment_method\": \"Salary Deduction\", \"batch_ref\": \"ISUCauFA-26-1\"}','Treasurer',24,'JASMINE ROTUGAL','112.198.120.53',NULL,NULL,'2026-07-25 11:32:17.697660',NULL,'28cdc70acfe8e5a24e2b4df9ed1650e59495bba68fecfa90709c282be37411d6','1655ca15ac7ed28b8df1ee71e7b9a1847d25fecfad3ea0941e953dce4975f9f9','879d0f9c39bd3aab4aabadd48628e41ce9e222e28969d1a4e846d3bb07d13d02'),
(67,'monthly_dues',3,'CREATED',NULL,'{\"member\": \"Jasmine Rotugal\", \"month_covered\": \"2026-03\", \"amount\": \"50.0\", \"payment_method\": \"Salary Deduction\", \"batch_ref\": \"ISUCauFA-26-1\"}','Treasurer',24,'JASMINE ROTUGAL','112.198.120.53',NULL,NULL,'2026-07-25 11:32:17.714756',NULL,'7c606328888128e62956759b3c00e2fd3eaab2cd566dee8bbb7a37fed72de2f6','333237a761b38d728e3f9fda54fb0eed987d07aca414262b817b4ac7e059dcf3','28cdc70acfe8e5a24e2b4df9ed1650e59495bba68fecfa90709c282be37411d6'),
(68,'monthly_dues',4,'CREATED',NULL,'{\"member\": \"Frederick H Zamboanga\", \"month_covered\": \"2026-03\", \"amount\": \"50.0\", \"payment_method\": \"Salary Deduction\", \"batch_ref\": \"ISUCauFA-26-1\"}','Treasurer',24,'JASMINE ROTUGAL','112.198.120.53',NULL,NULL,'2026-07-25 11:32:17.727981',NULL,'54321400ddfe61bc0be6abd573a6b5691265896f3b3daee43287bf6064f4d8e8','08ecb27c0197b7fd71114873d5843d39a8f73e638a2f38ccc54dca5282ffc4f1','7c606328888128e62956759b3c00e2fd3eaab2cd566dee8bbb7a37fed72de2f6'),
(69,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (1 records)','2026-07-25 11:46:14.519557',NULL,'9b3efb35d83691562c58983dea08b30a1205fafa4c848c8d7da3150ece37958a','cdfc6055c38d5fef8ea323403e2cfb2b8693692299190df964829de05d697820','54321400ddfe61bc0be6abd573a6b5691265896f3b3daee43287bf6064f4d8e8'),
(70,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-25 11:46:14.601366',NULL,'7234b9f7b8d80607edd72648d178fdcbd2119ddbe498bf220d14aef2619b08d2','71db49a01cee306acb5f99401e08eb6bb80216272be0fe00f080b12923f814e1','9b3efb35d83691562c58983dea08b30a1205fafa4c848c8d7da3150ece37958a'),
(71,'MONTHLY_DUES',4,'Treasurer Approved',NULL,NULL,'officer',24,'JASMINE ROTUGAL','212.102.51.117',NULL,'good','2026-07-25 11:46:36.074482',NULL,NULL,NULL,NULL),
(72,'MONTHLY_DUES',3,'Treasurer Approved',NULL,NULL,'officer',24,'JASMINE ROTUGAL','212.102.51.117',NULL,'','2026-07-25 11:46:43.142647',NULL,NULL,NULL,NULL),
(73,'MONTHLY_DUES',2,'Treasurer Approved',NULL,NULL,'officer',24,'JASMINE ROTUGAL','212.102.51.117',NULL,'','2026-07-25 11:46:48.823065',NULL,NULL,NULL,NULL),
(74,'MONTHLY_DUES',1,'Treasurer Approved',NULL,NULL,'officer',24,'JASMINE ROTUGAL','212.102.51.117',NULL,'','2026-07-25 11:46:54.707100',NULL,NULL,NULL,NULL),
(75,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (1 records)','2026-07-25 11:55:15.412261',NULL,'a900dc4d3ea471a0c7c23cf8712ecbefe351ecacbe9a93b211f0c2790957c0e9','1379682752c3e51cd44005e63efa3dd3434ea7e6bdcf907ee6c0a0e07b9c53fa','0000000000000000000000000000000000000000000000000000000000000000'),
(76,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-25 11:55:15.428897',NULL,'940cc7c592cea3b59c8d7ca631c4972daba5161b360c550d869e6a7acdd40e9e','acc1a222a7601dfe5aa7b04281918a2e11d2931936f26530e99fe76794121e99','a900dc4d3ea471a0c7c23cf8712ecbefe351ecacbe9a93b211f0c2790957c0e9'),
(77,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 00:11:04.312649',NULL,'1b202bccf86afb480204130f6b436a8086718f50aad04c7f6db0645711641273','adb6ee30b30bea2ed13e2e7b371b13b7b60b0d42883917343016be50f8e17dfa','940cc7c592cea3b59c8d7ca631c4972daba5161b360c550d869e6a7acdd40e9e'),
(78,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 00:11:04.659620',NULL,'31d8407123c496fb2ea159c17c4b4bc974ba27145ea08f1f9c8379bcc6178dfd','9feab6d7ce90c0b9e10446e6733a71bbdc702e23e43172591fd52edba0d61065','1b202bccf86afb480204130f6b436a8086718f50aad04c7f6db0645711641273'),
(79,'officer_user',30,'CREATED',NULL,'{\"id\": \"30\", \"full_name\": \"DEE JAY CRISTOBAL\", \"username\": \"secretary\", \"email\": \"vdark699@gmail.com\", \"role\": \"Secretary\", \"account_status\": \"Active\", \"term_start\": \"2026-07-31\", \"term_end\": \"2026-12-05\", \"department_id\": null, \"department_name\": null, \"department_code\": null, \"mfa_enabled\": \"False\", \"created_at\": \"2026-07-26T00:12:16.743692+00:00\", \"updated_at\": \"2026-07-26T00:12:16.743692+00:00\"}','President',23,'President Account','127.0.0.1',NULL,'Created officer account for DEE JAY CRISTOBAL','2026-07-26 00:12:16.748522',NULL,'bd3482c887c5e472e2b5a77aceff4744c8e197e7537ad0956de47d13dfcc706c','5c374d3b1297ab09bb73b4915f2329ead2298ff41c24497dcb0761481a914230','31d8407123c496fb2ea159c17c4b4bc974ba27145ea08f1f9c8379bcc6178dfd'),
(80,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 00:12:54.416541',NULL,'89151d52a8688e97ea9203f68dcfef40b41a9aaa6efc7e883061faabe30f7b1d','b84ea2fbab4396229ce57e79d1d154de306985f6b946bfc01cc04eddf8d798c4','bd3482c887c5e472e2b5a77aceff4744c8e197e7537ad0956de47d13dfcc706c'),
(81,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 00:12:54.754931',NULL,'e2010277857e985963f35c3b9d1cbd41679dd9e3930f521450a3aab6b5182803','0d33d53ab51d2fd36e0d419002599d7394112194f9e84484fece1184b6db5b62','89151d52a8688e97ea9203f68dcfef40b41a9aaa6efc7e883061faabe30f7b1d'),
(82,'officer_user',30,'UPDATED',NULL,'{\"id\": \"30\", \"full_name\": \"DEE JAY CRISTOBAL\", \"username\": \"secretary\", \"email\": \"vdark699@gmail.com\", \"role\": \"Secretary\", \"account_status\": \"Active\", \"term_start\": \"2026-07-31\", \"term_end\": \"2026-12-05\", \"department_id\": null, \"department_name\": null, \"department_code\": null, \"mfa_enabled\": \"False\", \"created_at\": \"2026-07-26T00:12:16.743692+00:00\", \"updated_at\": \"2026-07-26T00:13:06.482932+00:00\"}','President',23,'President Account','127.0.0.1',NULL,'Updated officer account for DEE JAY CRISTOBAL','2026-07-26 00:13:06.488602',NULL,'da8b9c1bc125651531b1c4620c0e7b3e1ff7bc8e9db39049ec2d371e5493c1c8','76b1e67e7894daefa4f8db4534f342470b7429c2f1da4a139929c40f6d7c9e77','e2010277857e985963f35c3b9d1cbd41679dd9e3930f521450a3aab6b5182803'),
(83,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 00:13:32.142808',NULL,'fa18d26c6abb30fbbb4df4a82eb4221b8dd21eccb758329f90ca191da57602f2','e4b0a516d309c58fcd008106ebaaf86f31cde97c11011045fb98b4b1b0906b29','da8b9c1bc125651531b1c4620c0e7b3e1ff7bc8e9db39049ec2d371e5493c1c8'),
(84,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 00:13:32.496454',NULL,'91fb5fd752634207ccf00f810b7a9e1833dbb6674c043ef468cda0e22e3607f6','abeb9bf307c4f31ff012dacd0c942349dc83bce5bccf43a9c92080d2e48fc0ad','fa18d26c6abb30fbbb4df4a82eb4221b8dd21eccb758329f90ca191da57602f2'),
(85,'officer_user',30,'UPDATED',NULL,'{\"id\": \"30\", \"full_name\": \"DEE JAY CRISTOBAL\", \"username\": \"secretary\", \"email\": \"vdark699@gmail.com\", \"role\": \"Secretary\", \"account_status\": \"Active\", \"term_start\": \"2026-07-26\", \"term_end\": \"2026-12-05\", \"department_id\": null, \"department_name\": null, \"department_code\": null, \"mfa_enabled\": \"False\", \"created_at\": \"2026-07-26T00:12:16.743692+00:00\", \"updated_at\": \"2026-07-26T00:13:46.454176+00:00\"}','President',23,'President Account','127.0.0.1',NULL,'Updated officer account for DEE JAY CRISTOBAL','2026-07-26 00:13:46.456259',NULL,'093358a4a79617797892d29c67ca71e86957886acaf9763c1466a94cb2bef65a','8fa983a115ad766bade6699f5cbfd4e6057f9037b686bcc891d3f360e02b90a9','91fb5fd752634207ccf00f810b7a9e1833dbb6674c043ef468cda0e22e3607f6'),
(86,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 08:21:58.665549',NULL,'c7c9c0ade7a95591442512ca54ed96be0519293d5d4b0b9936ae7ac6e1675840','5c815497d0d012c9efba59fd2173275943b005d02cfe972711702a95bdd30aa7','093358a4a79617797892d29c67ca71e86957886acaf9763c1466a94cb2bef65a'),
(87,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 08:21:59.266034',NULL,'66b708fc9efa293ab011ffec31530ce2c9788ed6c9ddf18bb1881976e407bc8e','18515e9b07dfef6ac207aaef40f617e21855e6b53ed8992745522e429a03bc35','c7c9c0ade7a95591442512ca54ed96be0519293d5d4b0b9936ae7ac6e1675840'),
(88,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (1 records)','2026-07-26 08:22:11.018176',NULL,'d9d56b15c142b13e0bb5ce9cc1cb8c4e7ee07e784968a70374ab156bdd034f03','00bf8e8eb16b3b720ad898bd73dc42db5e64253912b36bfc6208db13171202c2','66b708fc9efa293ab011ffec31530ce2c9788ed6c9ddf18bb1881976e407bc8e'),
(89,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-26 08:22:11.131837',NULL,'4c607eac3a5eec740f7b62fb65ffefed0fdd3ca519801b7ed5726d2c6878d798','ae89b304f7fe0b0b59690654da7bab6a1c33898146a55c3daca893ca945ec4f3','d9d56b15c142b13e0bb5ce9cc1cb8c4e7ee07e784968a70374ab156bdd034f03'),
(90,'officer_user',25,'UPDATED',NULL,'{\"id\": \"25\", \"full_name\": \"FREDERICK MADAYAG\", \"username\": \"auditor\", \"email\": \"programmingproject06@gmail.com\", \"role\": \"Auditor\", \"account_status\": \"Active\", \"term_start\": \"2026-07-01\", \"term_end\": \"2026-08-01\", \"department_id\": null, \"department_name\": null, \"department_code\": null, \"mfa_enabled\": \"True\", \"created_at\": \"2026-07-25T10:22:01.950602+00:00\", \"updated_at\": \"2026-07-26T08:23:18.542155+00:00\"}','President',23,'President Account','127.0.0.1',NULL,'Updated officer account for FREDERICK MADAYAG','2026-07-26 08:23:18.556160',NULL,'bc5c57b48d835a524671dfde1e25caea1d99506edf133f46528e2f5b8df4a367','f0290a53be5661cd6b12bcf378f3d78b9be84fc1c498e4855d98222d518232a0','4c607eac3a5eec740f7b62fb65ffefed0fdd3ca519801b7ed5726d2c6878d798'),
(91,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 08:30:57.623449',NULL,'79b99c88c0f3693eb4aab0b382c981b1e52d0e26a2ed8cf203cc5e0799de036c','5e070a0bddcd12556838d0acfa6155c9b2f62a98024579886f0ae76e8eb6fe8e','bc5c57b48d835a524671dfde1e25caea1d99506edf133f46528e2f5b8df4a367'),
(92,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 08:30:58.995732',NULL,'2eb9b37003cba73a946d116343790ac1541a431a02eabc8f0bd208f656367377','c3f6a8ae1184e9392fa136f878fc1a69e5b08da9cdaaefb8406e77c5edde8c30','79b99c88c0f3693eb4aab0b382c981b1e52d0e26a2ed8cf203cc5e0799de036c'),
(93,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (1 records)','2026-07-26 08:31:10.739405',NULL,'6596f4c3f58d7428b07f07a3bc1d02ece6f5de03c6c59a11c2514789a5b671b5','d8401aa7598a3a3672b40ae5e6293cfdcd472efe34641bbd7f5d9d347d065f0a','2eb9b37003cba73a946d116343790ac1541a431a02eabc8f0bd208f656367377'),
(94,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-26 08:31:11.145128',NULL,'389738ea3561b61a0c5b307df89cc0af0106f8372327a62154faf8a8df98bb74','d3e1c1bf5b72fa9c8a46ca10a482774da75631d4f78419bcd60a57eb4a5cf679','6596f4c3f58d7428b07f07a3bc1d02ece6f5de03c6c59a11c2514789a5b671b5'),
(95,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 08:31:21.434617',NULL,'fdd6bc305ba54b1d72eca2e8f38127064dc4f7438e24f2ecdf4d8da74bca57e2','a363477670df71a20cc79f127582acaf94bd6feb86ee1639b2089e03db5add49','389738ea3561b61a0c5b307df89cc0af0106f8372327a62154faf8a8df98bb74'),
(96,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (1 records)','2026-07-26 08:31:24.646671',NULL,'e0d99bbddb767547dae579a96c04a4c4e8caa79899141b152a403092d6bfb798','ef7de4c9132273a7e75231c79fccd9027c031ec409de9b509eca898e4d438122','fdd6bc305ba54b1d72eca2e8f38127064dc4f7438e24f2ecdf4d8da74bca57e2'),
(97,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-26 08:31:24.840007',NULL,'32040a79c79a6e421f3de4f93959f2ff698fef5521e3e012aeaaf6912d076ddd','744bd90f65b14d95e2389cd69a01aa7646ac5c78b550e5f5a0cca2506f405c28','e0d99bbddb767547dae579a96c04a4c4e8caa79899141b152a403092d6bfb798'),
(98,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (1 records)','2026-07-26 08:31:35.975564',NULL,'d2a1d83dcfaa5d6fd974bba184d86b29644b9ee4aa2a763d2866457de65d120c','69c698cec53f99498180230b98f1b8435169cb55e116af1d0007dfefde01dbef','32040a79c79a6e421f3de4f93959f2ff698fef5521e3e012aeaaf6912d076ddd'),
(99,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-26 08:31:36.276746',NULL,'f759b8c455567bf54a63d3517d4821316fc92e1c06b4cfa98600f444d2f26754','5e1975734130949fdbf76ce6cfd3eb3594a25bb7d64c944df950a3452c43902b','d2a1d83dcfaa5d6fd974bba184d86b29644b9ee4aa2a763d2866457de65d120c'),
(100,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (1 records)','2026-07-26 08:31:45.604315',NULL,'280931cc893d7d2b8473857e372cb4172ff0efa49e68c42f7f81557588e7082d','d58074515650254148fd69d5a4e395e4b3a07b629470327f02b4c4977aa7e944','f759b8c455567bf54a63d3517d4821316fc92e1c06b4cfa98600f444d2f26754'),
(101,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-26 08:31:45.793672',NULL,'cc3b3d4fb8f833d5fd17bdf5dce151827b7a7719a4f978543c3486287eeaebc1','c8de8e953114c38f8f1e18d888cc6c459657e7ccf089df422a16bae077ab9b07','280931cc893d7d2b8473857e372cb4172ff0efa49e68c42f7f81557588e7082d'),
(102,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (1 records)','2026-07-26 08:32:05.179671',NULL,'1b106a824921a761d6680bf153afc51101bee36dba0d24f03a6a2e34e17fcb5a','f0ff1eedbaf48031b8c7f8b6dcd74a6f9e032c8cc1d4e94a173debf1b6ddc8a0','cc3b3d4fb8f833d5fd17bdf5dce151827b7a7719a4f978543c3486287eeaebc1'),
(103,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-26 08:32:05.428414',NULL,'19f2ecc4982b6345d0c8480455f519635a1fbd65cedb8ec00916da320edfafce','6b68f67ce75d896b9a11a23f55a82e9aa6e7bf9533670a8959c5d636fb860323','1b106a824921a761d6680bf153afc51101bee36dba0d24f03a6a2e34e17fcb5a'),
(104,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (1 records)','2026-07-26 08:32:27.353505',NULL,'f8877c0e200c0d58458cbde7ba3493f9d764598eb5470a9bfd9293a00c1d4960','3d0fb5381e176e24432cae223a1a1d692d846be185b65b033be1c1e2d0543ba0','19f2ecc4982b6345d0c8480455f519635a1fbd65cedb8ec00916da320edfafce'),
(105,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-26 08:32:27.456994',NULL,'42de2ea1df1d5439869c7f5068c26b7c1476fa1a2c718b296c81c7f4171bc041','e8cd6ed2a1a54eaf5dd803ae24d7e0f52b964b9a71eeab7df5b3e23e3e71d162','f8877c0e200c0d58458cbde7ba3493f9d764598eb5470a9bfd9293a00c1d4960'),
(106,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (1 records)','2026-07-26 08:32:42.697565',NULL,'9933546c20cafa8e3dfcdb40dece2547985c1691ebcc2bb4bdf4026521edb632','cc358846ff1af1eb62a4bc927f3222a23b2a83f96ed97b1418f851c43200921d','42de2ea1df1d5439869c7f5068c26b7c1476fa1a2c718b296c81c7f4171bc041'),
(107,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-26 08:32:43.045968',NULL,'25447a6e23423875c3bca66341364ce31b4b36414bf9a46da85034a3ec4af9e6','dac1316faca00cf1f8eacd5752584dfaebd8dc596bc7197b39635127bdcd819b','9933546c20cafa8e3dfcdb40dece2547985c1691ebcc2bb4bdf4026521edb632'),
(108,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (1 records)','2026-07-26 08:35:17.027151',NULL,'082ec17a9451d5c1ecc852cd9f91acbdb892151b5960f05d3c985912da69f0c2','bd6b4bbfe7008564718fa605c436318dc2a9d36fd78e3cc2700acd07fab1e69f','25447a6e23423875c3bca66341364ce31b4b36414bf9a46da85034a3ec4af9e6'),
(109,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-26 08:35:17.578009',NULL,'b24eaa14ce710e6dae9be08309f06520d3e1dbc5230b9022fddb74e274ab66dc','fff80cfa053b77c6239b793fc14bb71b8f8661249b4c205fa32eabe0658edbf3','082ec17a9451d5c1ecc852cd9f91acbdb892151b5960f05d3c985912da69f0c2'),
(110,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (1 records)','2026-07-26 08:35:50.285457',NULL,'bcbac67c75fca1db1ff2abdebeb680f97e8393d03a49a9936b9a54731e33f8df','dc3059b84d4009cec26433389d4d5f3387d80f3316d3e9818b16525e7f794105','b24eaa14ce710e6dae9be08309f06520d3e1dbc5230b9022fddb74e274ab66dc'),
(111,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-26 08:35:50.785722',NULL,'0372b6edfeca7d0072c484c0a923834810d74cacb49a62de91a7d1592a88e32a','64d50d6f2cea39ca8f2b01abee90ce10667329db8d9f853b792e1f6d743cc82a','bcbac67c75fca1db1ff2abdebeb680f97e8393d03a49a9936b9a54731e33f8df'),
(112,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (1 records)','2026-07-26 08:35:59.343309',NULL,'f82fd66ab7524da29006d29477cf838f655cb782986c1d33d9a524e70b93d7cc','6ff5b721119b846e8740ee8ec86fec31edd2a31538f0ad624ac5f580212e3e8a','0372b6edfeca7d0072c484c0a923834810d74cacb49a62de91a7d1592a88e32a'),
(113,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-26 08:35:59.921284',NULL,'22b98ca14369b3b63ed9869781886ab88e833fa78a21c29c8da5c8e6a0ab08cd','5afecf11ab1f3bce9b3a07d4fbdae390dbc37b8bde26855f05b5761fe74f8d5b','f82fd66ab7524da29006d29477cf838f655cb782986c1d33d9a524e70b93d7cc'),
(114,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (1 records)','2026-07-26 08:36:30.217908',NULL,'1086e17036498166e2279827195777d04e713535eeb300857832dea6494030ad','5190eb42502e36f3a3b0d205b941cf81b27df495a67afca193a61160fb796252','22b98ca14369b3b63ed9869781886ab88e833fa78a21c29c8da5c8e6a0ab08cd'),
(115,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-26 08:36:30.393108',NULL,'51e7cfc16df0cda493570117816cf953ba95ec8e08252e59252e3ce6ca0e4dbe','3f380987c1dd1065184ff3c56ab50bf2c0f1940c2fcecd6942cb1dc4209b4d4a','1086e17036498166e2279827195777d04e713535eeb300857832dea6494030ad'),
(116,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (1 records)','2026-07-26 08:37:02.808347',NULL,'55b2d048fad34c6264a07f004732d6d6ec9578559e8f50736b33a4918b17f7f5','79d66f58c0ccf0856d8827f4612b01c0582ca3eca834815099554bebd6341c52','51e7cfc16df0cda493570117816cf953ba95ec8e08252e59252e3ce6ca0e4dbe'),
(117,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-26 08:37:03.103498',NULL,'c85010c656370112bd94524279838e794599441508019306251c9a77130ed4e9','5bc2ae4cdd783208bc252a96d030f579028c1b0c14e5b85b8da5ed4a2ff8acb3','55b2d048fad34c6264a07f004732d6d6ec9578559e8f50736b33a4918b17f7f5'),
(118,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (1 records)','2026-07-26 08:37:30.400740',NULL,'d95d18a7fe0730bca4c37cbb36ce1049806f846bf856ea830f52cf5811af14fb','24799dab9e116be4e185580223116534ad69ec4a86cd8a960cb2f3c04ea12c6a','c85010c656370112bd94524279838e794599441508019306251c9a77130ed4e9'),
(119,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-26 08:37:30.580739',NULL,'40b5fc90d598d5237fa8455c67042d8e619d5fd6a80eca69c55b18b2175e4704','db7de68f2bdadc061f443128796b0f4088d4ff717f592c6fae97252f06b654d9','d95d18a7fe0730bca4c37cbb36ce1049806f846bf856ea830f52cf5811af14fb'),
(120,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (1 records)','2026-07-26 08:44:06.323860',NULL,'7ee011ab74bc9f00f85e92979319b83aed8d9d3545b393947c822c7cb6c3482d','83e68c7f49118f9a669da9e73be8a78fe0ce375a98d5f8ed830434a54ec51c41','40b5fc90d598d5237fa8455c67042d8e619d5fd6a80eca69c55b18b2175e4704'),
(121,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-26 08:44:06.615511',NULL,'e10c55d91530cc457660a36973f97119819fd401c8355f0c89ddbbba13335294','f6b436318cd7a17a71216c8f2d24e1a365ef888d10b6e1dcfeb3d4e185d7dc30','7ee011ab74bc9f00f85e92979319b83aed8d9d3545b393947c822c7cb6c3482d'),
(122,'member_registration_request',5,'TREASURER_VERIFIED',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1',NULL,'Treasurer verified registration request for JOHN PAUL R Versoza','2026-07-26 08:44:46.740152',NULL,'55937ce4364ea2674fc2af9605c89a4705ab663a7f507d1fe178fc350c31ed8d','93fc2f77545dc98b492f116ef6391649f4c5b02909f1867f81784a5f6b597a5d','e10c55d91530cc457660a36973f97119819fd401c8355f0c89ddbbba13335294'),
(123,'member_registration_request',5,'AUDITOR_VERIFIED',NULL,NULL,'Auditor',25,'FREDERICK MADAYAG','127.0.0.1',NULL,'Auditor verified registration request for JOHN PAUL R Versoza','2026-07-26 08:46:29.270399',NULL,'085524b054da696f739fddcfc6a29c2319017ed91984c265c7f3f3c4f9a518a3','b6e956b932dbc321d53d58569c092b0405847f47e1d1b8236c197a8ff6fc7c40','55937ce4364ea2674fc2af9605c89a4705ab663a7f507d1fe178fc350c31ed8d'),
(124,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 08:46:49.131575',NULL,'773c60ef418ee80be7ae642e9ca1f3574b7a996c0a304b8bc8574109db29af26','a1997a07463917fcda577647acc899ae51ef682a55a61b59c49b389e2922caaa','085524b054da696f739fddcfc6a29c2319017ed91984c265c7f3f3c4f9a518a3'),
(125,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 08:46:49.829638',NULL,'90491ec595a0caa16dd4fa423764276352a9a0f61f62ddae8992f9d1515faebe','2876f3cd66cf2b3a888be2ca695e1e358d8dfe6bb29f592c40e9f5ec083b3550','773c60ef418ee80be7ae642e9ca1f3574b7a996c0a304b8bc8574109db29af26'),
(126,'member_registration_request',5,'PRESIDENT_APPROVED',NULL,'{\"member_id\": \"5\", \"officer_user_id\": \"31\", \"fee_id\": \"5\", \"status\": \"President Approved\"}','President',23,'President Account','127.0.0.1',NULL,'President approved registration for JOHN PAUL R Versoza. Member/OfficerUser/MembershipFee created.','2026-07-26 08:47:46.241744',NULL,'add4c13d3ab2991f116266e7671a2b08fefe14ee1f4a6ed8b798a78bebbd7ac6','18e91ba1ad6112242b3a5231805937548c48b641003abec353e943d6c33da771','90491ec595a0caa16dd4fa423764276352a9a0f61f62ddae8992f9d1515faebe'),
(127,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 08:49:12.056332',NULL,'1cd51be26cfde09539f3b68d2ba176218b5594d522c9f3fd05e89d63cb3271be','820344de6c28edd2c910a9ff6d1bfcd087a94c65805ba88835da80aab6b93e94','add4c13d3ab2991f116266e7671a2b08fefe14ee1f4a6ed8b798a78bebbd7ac6'),
(128,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 08:49:13.309527',NULL,'7b414f8b8ae42f06ac9e1df6b3d81c2f9c6f9ecff0193dfa5e8e6a1954746c79','5f50f687abf054231184028c97beec6259ad1b58f8c2d4d8e4fda730dc2012db','1cd51be26cfde09539f3b68d2ba176218b5594d522c9f3fd05e89d63cb3271be'),
(129,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (1 records)','2026-07-26 08:49:14.403704',NULL,'de379440bce377818a7ef0c4bc9821a9d589bbd87b06fd4f168a96340dd1a4f3','ae818ceb54135f5315c1eea73e32dda4268a1aed2981142a0d153337041c351e','7b414f8b8ae42f06ac9e1df6b3d81c2f9c6f9ecff0193dfa5e8e6a1954746c79'),
(130,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-26 08:49:14.632709',NULL,'e223955dafc47308b577a45ba9b5621f78ad4d943d9314968936d81df079ef47','0039a33aefb56cfa9712c90b1ee2987a7c811f711293fb043f9071da61a9e6cc','de379440bce377818a7ef0c4bc9821a9d589bbd87b06fd4f168a96340dd1a4f3'),
(131,'officer_user',31,'UPDATED',NULL,'{\"id\": \"31\", \"full_name\": \"JOHN PAUL R Versoza\", \"username\": \"142joe\", \"email\": \"bermuda.66891@gmail.com\", \"role\": \"Member\", \"account_status\": \"Active\", \"term_start\": null, \"term_end\": null, \"department_id\": null, \"department_name\": null, \"department_code\": null, \"mfa_enabled\": \"False\", \"created_at\": \"2026-07-26T08:47:46.191822+00:00\", \"updated_at\": \"2026-07-26T08:49:37.460420+00:00\"}','President',23,'President Account','127.0.0.1',NULL,'Updated officer account for JOHN PAUL R Versoza','2026-07-26 08:49:37.479088',NULL,'56a2ddde71045f3271c9ac2c573f64e55e2401c9a2939c2e5f4df1c856f6aa5b','2f6f15445ae24ad80356f12e64a0be925e0c86f3b6f10ec76ce866ab03cdd8b4','e223955dafc47308b577a45ba9b5621f78ad4d943d9314968936d81df079ef47'),
(132,'officer_user',31,'DEACTIVATED',NULL,'{\"id\": \"31\", \"full_name\": \"JOHN PAUL R Versoza\", \"username\": \"142joe\", \"email\": \"bermuda.66891@gmail.com\", \"role\": \"Member\", \"account_status\": \"Inactive\", \"term_start\": null, \"term_end\": null, \"department_id\": null, \"department_name\": null, \"department_code\": null, \"mfa_enabled\": \"False\", \"created_at\": \"2026-07-26T08:47:46.191822+00:00\", \"updated_at\": \"2026-07-26T08:49:45.959675+00:00\"}','President',23,'President Account','127.0.0.1',NULL,'Deactivated officer account for JOHN PAUL R Versoza','2026-07-26 08:49:45.968931',NULL,'f67f37de3a24a8f7c50d9372dd361038f0aedc69f57e50730dbcb9cc8daf4e33','b3146e22f225c6ee4f1af651961e28999119fd657efc560535ec7cae470c1655','56a2ddde71045f3271c9ac2c573f64e55e2401c9a2939c2e5f4df1c856f6aa5b'),
(133,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 08:55:27.135584',NULL,'52c634f15cefc3effba4220ca80fb2caa7fed3aca5b4eabf73264d24cc59ac3b','97467601cee0fc6ffc0e5e9506296f4fe34bc2facafc9f28cf0059105781e9aa','f67f37de3a24a8f7c50d9372dd361038f0aedc69f57e50730dbcb9cc8daf4e33'),
(134,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 08:55:28.808501',NULL,'643b96b28a1e1ef054a6f03e055574c5a9a00b9e629a9fe472986a7112fed7a9','67940c9f2a444d009a37f3497d5526078120f6c059cfa77ac6f2b43b4174b0c2','52c634f15cefc3effba4220ca80fb2caa7fed3aca5b4eabf73264d24cc59ac3b'),
(135,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (1 records)','2026-07-26 08:55:29.853588',NULL,'42b7dcdd8895797e194999d147da717159eb3c71e2dee336e4f8567137923a6b','0dd43c72382139b8c54f200fb898595448489919b2a26c3cb1e460b4ed67774b','643b96b28a1e1ef054a6f03e055574c5a9a00b9e629a9fe472986a7112fed7a9'),
(136,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-26 08:55:30.147596',NULL,'380d4248536925737df680283c395551b64ef6207b7c30186187ca31e6fa579a','4a65ad616945e6b59c2d7259f4c4d60309f953105b6ed0c3ea93d4c7d422d31d','42b7dcdd8895797e194999d147da717159eb3c71e2dee336e4f8567137923a6b'),
(137,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 08:57:49.687019',NULL,'810532c37e28be8c780275eda7e6d755ce6c615b97dc5c4c3ebe133f388b49e4','97f14ba82952f274f1aa364fa82638dbadd7932ae79c88cfcce7b22841534486','380d4248536925737df680283c395551b64ef6207b7c30186187ca31e6fa579a'),
(138,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 08:57:51.335186',NULL,'f84ba220460748ca5bad61fc42cc513cb5a942aa8703174b075dfdfb461aac5e','987cdd649e20c5ae996ba5afdfdf9d568bcd7f6082c15fbbf6d708cb32a49942','810532c37e28be8c780275eda7e6d755ce6c615b97dc5c4c3ebe133f388b49e4'),
(139,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (1 records)','2026-07-26 08:57:53.621471',NULL,'7bdd9491d382c7c1a131bf5e24041474d35c4087286ab34f60695e9f380192c5','b73ee78c706f7092bd195b410960f0b0fe114307fe1abacde6d3e3145eabceab','f84ba220460748ca5bad61fc42cc513cb5a942aa8703174b075dfdfb461aac5e'),
(140,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-26 08:57:54.122490',NULL,'9a6b0e4a6e319c53a7b742d43b40e0900498a26c950cd3d64c66efaaede501f4','5a27e23366a77394b13f2cf98398747ed21c34dedde753a4198da517cc3e0feb','7bdd9491d382c7c1a131bf5e24041474d35c4087286ab34f60695e9f380192c5'),
(141,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 08:59:16.152749',NULL,'ec58e5d102cb86c1923613c0ebb2be16aa035561ed16f41bd3a944fc689e03f3','345e95452bfa360b9dabbaf93f4dd9ba98c0dedc8e50ba2517dc499cd9ba68f5','9a6b0e4a6e319c53a7b742d43b40e0900498a26c950cd3d64c66efaaede501f4'),
(142,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 08:59:17.301168',NULL,'170bce279481bcf35898698700f3c54d9f27097e222abb3ff7a6617ddfd42250','4bf55cc2100828cd44ea32256fcb4c3f49b680c5324c96b75b611703335a81db','ec58e5d102cb86c1923613c0ebb2be16aa035561ed16f41bd3a944fc689e03f3'),
(143,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (1 records)','2026-07-26 08:59:18.222848',NULL,'96fa24bde6a6e18e8ddefc5a89094c896eaf09907f06139e50c25c1a2a248247','2b56fe5c0ca21ee64f88ff1e66c64e41c15fea07090ec0d8fe1a0e2f7cbea591','170bce279481bcf35898698700f3c54d9f27097e222abb3ff7a6617ddfd42250'),
(144,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-26 08:59:18.403401',NULL,'5e03dcfc1c33f5b56b8b606ad05f056964ff8849f96306df5117fb20be155e43','a70741bcea4dfcfe340567a4aeb8b4e1eac9cd0cfdd798969fb77f91aaefffc0','96fa24bde6a6e18e8ddefc5a89094c896eaf09907f06139e50c25c1a2a248247'),
(145,'officer_user',31,'UPDATED',NULL,'{\"id\": \"31\", \"full_name\": \"JOHN PAUL R Versoza\", \"username\": \"142joe\", \"email\": \"bermuda.66891@gmail.com\", \"role\": \"Member\", \"account_status\": \"Inactive\", \"term_start\": null, \"term_end\": null, \"department_id\": null, \"department_name\": null, \"department_code\": null, \"mfa_enabled\": \"False\", \"created_at\": \"2026-07-26T08:47:46.191822+00:00\", \"updated_at\": \"2026-07-26T09:01:18.227584+00:00\"}','President',23,'President Account','127.0.0.1',NULL,'Updated officer account for JOHN PAUL R Versoza','2026-07-26 09:01:18.237671',NULL,'89fea6fa11c91cdfb402bdd76273b8395a613953005b526c84a4e10655b48e9b','edf6c1c6c5c68a953f39e05d65a26c47f9e8e9bfe48774f2265d820bc12f0b6d','5e03dcfc1c33f5b56b8b606ad05f056964ff8849f96306df5117fb20be155e43'),
(146,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 09:01:21.757940',NULL,'72b5f832397f30b516d9c3f1d4a21950a5f4b8ced6b2f303ec08334a3c43ab5a','e54a9eb574bb10895556d6643405bc0fbb0fbd5950f6dd2c006fc9ad1ff015de','89fea6fa11c91cdfb402bdd76273b8395a613953005b526c84a4e10655b48e9b'),
(147,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 09:01:22.439842',NULL,'acde5ff8f2c539e57daa3acdadf8383b492269423baaf99b7ea6524336044f1b','68f37a01aa7b16ce18adb09589b72743072301adce8a921445ee3ca94856f89f','72b5f832397f30b516d9c3f1d4a21950a5f4b8ced6b2f303ec08334a3c43ab5a'),
(148,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (1 records)','2026-07-26 09:06:18.060869',NULL,'8058bab6c0cc1a0f2293d271da19725585b21df04e889d1e39d368b3d9d0cd9e','ba26998d7a4a5f88114e3559477452bef6b87dd49b9c32e161570d7403da0783','acde5ff8f2c539e57daa3acdadf8383b492269423baaf99b7ea6524336044f1b'),
(149,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 09:06:18.209092',NULL,'e5cee2fa4dc913eae1abfa43635bfce265527adf9619bff63a3a73c4107db043','80f43509cba82cd34a13cf115558a975405d3eb1b14b829dc2e53606033747f8','8058bab6c0cc1a0f2293d271da19725585b21df04e889d1e39d368b3d9d0cd9e'),
(150,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-26 09:06:18.348852',NULL,'4df97d9b8e190a8a6620b8efd33612236d7f29b7073355ea98abfabe56614ad4','f311afa261ee4064e4f7ce5b0f45b4fd14f600141460866541a4dcbc68aa2bcf','e5cee2fa4dc913eae1abfa43635bfce265527adf9619bff63a3a73c4107db043'),
(151,'member_registration_request',6,'TREASURER_VERIFIED',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1',NULL,'Treasurer verified registration request for JUSTIN VON T VERGARA','2026-07-26 09:09:11.849723',NULL,'8d33c99534422dc69910120dfafc2c1e6feae0f7ec4e12d60198ce40842f0595','eeff7c2c69b7eac65e17704fee81ad5c7594d0de7f7a2bb6e33a1ded3bc63060','4df97d9b8e190a8a6620b8efd33612236d7f29b7073355ea98abfabe56614ad4'),
(152,'member_registration_request',6,'AUDITOR_VERIFIED',NULL,NULL,'Auditor',25,'FREDERICK MADAYAG','127.0.0.1',NULL,'Auditor verified registration request for JUSTIN VON T VERGARA','2026-07-26 09:10:04.825914',NULL,'59daa59245b7c9d86dcb1b7cb3b742f9bc0b7efe54f5e476ecf10e3901122a27','b844c592c8cc0d22cb440a77bf17ecf86519cd63dcac7b60076e7c2ae7aff858','8d33c99534422dc69910120dfafc2c1e6feae0f7ec4e12d60198ce40842f0595'),
(153,'member_registration_request',6,'PRESIDENT_APPROVED',NULL,'{\"member_id\": \"6\", \"officer_user_id\": \"32\", \"fee_id\": \"6\", \"status\": \"President Approved\"}','President',23,'President Account','127.0.0.1',NULL,'President approved registration for JUSTIN VON T VERGARA. Member/OfficerUser/MembershipFee created.','2026-07-26 09:10:44.689020',NULL,'55bb87dafb6db6f1f79c0920513d1bfaa48b983b61f6c4178034064e1bb8fcf4','33a6e8bf852b25a70948345acc830a4216491be295a3ca5ed5c97d8308a1025a','59daa59245b7c9d86dcb1b7cb3b742f9bc0b7efe54f5e476ecf10e3901122a27'),
(154,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 09:12:21.847099',NULL,'99853fd3bda746be587d4ae5b7217a2efef971882366f7cdc062982681fdaf44','1b00aedd3eab4df9261db7013e69f32c811004cca39451d31bc88c0c94c3443a','55bb87dafb6db6f1f79c0920513d1bfaa48b983b61f6c4178034064e1bb8fcf4'),
(155,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 09:12:22.946031',NULL,'bc64cbedba38451923748ec3197ac905ab338cfdb4b07030289cf731f01e4a8e','7685de9d5871833168210b56c71e5d8147e001c8a426a6ffbd3ff96745310875','99853fd3bda746be587d4ae5b7217a2efef971882366f7cdc062982681fdaf44'),
(156,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (1 records)','2026-07-26 09:12:23.915379',NULL,'8c5da1757851b0023069b45fa340e02813c65bf59bc011f82a815cece6606b10','4fb3a59092389bb5cf382d1b2344b78831ecb0ee44ce525b39839f98ec607e37','bc64cbedba38451923748ec3197ac905ab338cfdb4b07030289cf731f01e4a8e'),
(157,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-26 09:12:24.106888',NULL,'49381652e3e570501adff82493e35b8f058384f406e1083a034395e6104a9a2e','ff2e46ed39a3b94da8567a105a4aabc684ee0219ecf85f123e1e4e60e45c8cbf','8c5da1757851b0023069b45fa340e02813c65bf59bc011f82a815cece6606b10'),
(158,'member_registration_request',7,'TREASURER_VERIFIED',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1',NULL,'Treasurer verified registration request for JUSTIN VON T VERGARA','2026-07-26 09:15:24.535853',NULL,'3d9b753689e0f894719ed98f2865efba3f95f49c31d3cdb5aee63e4fc2613845','d87651cc28e5c55091c8b5eac283a77c36d57c882e3f8670e95b77864d0c77b4','49381652e3e570501adff82493e35b8f058384f406e1083a034395e6104a9a2e'),
(159,'member_registration_request',7,'AUDITOR_VERIFIED',NULL,NULL,'Auditor',25,'FREDERICK MADAYAG','127.0.0.1',NULL,'Auditor verified registration request for JUSTIN VON T VERGARA','2026-07-26 09:16:10.045582',NULL,'8a936ddb51c8b7722e39683ae969e42c3e867d5f38925a6334d23cd281b70a41','61cab9458078acfe5ab1c6c3cff90343df8591665d39d6c2618928412922eeea','3d9b753689e0f894719ed98f2865efba3f95f49c31d3cdb5aee63e4fc2613845'),
(160,'member_registration_request',7,'PRESIDENT_APPROVED',NULL,'{\"member_id\": \"7\", \"officer_user_id\": \"33\", \"fee_id\": \"7\", \"status\": \"President Approved\"}','President',23,'President Account','127.0.0.1',NULL,'President approved registration for JUSTIN VON T VERGARA. Member/OfficerUser/MembershipFee created.','2026-07-26 09:16:52.853113',NULL,'0d54a51e92fbe0f609fa423080212700023f9d280316a5a0df1501d3f0d0a51d','285388c299e5a46e1cfed9a9c12b1953147d5d2c4c27e209fb94c108331fb900','8a936ddb51c8b7722e39683ae969e42c3e867d5f38925a6334d23cd281b70a41'),
(161,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 09:21:22.231598',NULL,'49c9472db5fa4f6666da3b180eb658bd4d9c21955cf20101b0edd4b9d335f045','64859035f566129970123c651373bac824761d75bb27b1c5121025cde02a7dd7','0d54a51e92fbe0f609fa423080212700023f9d280316a5a0df1501d3f0d0a51d'),
(162,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 09:21:23.372386',NULL,'b92cb4912d18600a3e2e8cd68e27fbcf35ab960a28eb68e6eed03f4cd0ca7b80','ef0fb91e00b1169305f3da5286eb9c9b3ba21aa776cccdd16019ec1d8faf2d4b','49c9472db5fa4f6666da3b180eb658bd4d9c21955cf20101b0edd4b9d335f045'),
(163,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (1 records)','2026-07-26 09:21:24.096187',NULL,'78175a6b04d54c3f24a1e6157e50000373bb8c3b34f24a2b9c33acedf3cd1ad0','ed2207a1b4e239b737028033a9c9bc2a86b1c5e92902b1e317c70a8d15c4e004','b92cb4912d18600a3e2e8cd68e27fbcf35ab960a28eb68e6eed03f4cd0ca7b80'),
(164,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-26 09:21:24.234050',NULL,'d7a98a6a8d843c318d8b28b2113a3a99a7fb642150e97fb4643a0cd6ce30a6f2','61530753dee69d4ef3f03487093ce1b4ef7c592cd12dd47edcf5aad7534dcb5f','78175a6b04d54c3f24a1e6157e50000373bb8c3b34f24a2b9c33acedf3cd1ad0'),
(165,'member_registration_request',8,'TREASURER_VERIFIED',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1',NULL,'Treasurer verified registration request for JOHN PAUL R VERSOZA','2026-07-26 09:24:36.695277',NULL,'8f5b89bc247e34e1a7f25a963c60ccf50c9461c87e2c8bba93d470c9010f949f','5695d1ae39d84d7ab6b7a779c063b12da36657de23707577ea2493ee1fea94ff','d7a98a6a8d843c318d8b28b2113a3a99a7fb642150e97fb4643a0cd6ce30a6f2'),
(166,'member_registration_request',8,'AUDITOR_VERIFIED',NULL,NULL,'Auditor',25,'FREDERICK MADAYAG','127.0.0.1',NULL,'Auditor verified registration request for JOHN PAUL R VERSOZA','2026-07-26 09:25:27.697163',NULL,'58824edff626a0f4fb7ab96d8004999dda67a7b01869ae2e0243da07974a010b','8c7af87a5f86c8fc5e6cb34408c9853d5064463fcecbc847929ea3f350836ffe','8f5b89bc247e34e1a7f25a963c60ccf50c9461c87e2c8bba93d470c9010f949f'),
(167,'member_registration_request',8,'PRESIDENT_APPROVED',NULL,'{\"member_id\": \"8\", \"officer_user_id\": \"34\", \"fee_id\": \"8\", \"status\": \"President Approved\"}','President',23,'President Account','127.0.0.1',NULL,'President approved registration for JOHN PAUL R VERSOZA. Member/OfficerUser/MembershipFee created.','2026-07-26 09:26:08.808258',NULL,'f38f37d9d66f260ce4f9a938781921116aceba94fad7468115b219950f891bfe','b711893d6d4d3b0abdbee02ac6b722887dbba4f7c8abef8d075ac1e0f693151b','58824edff626a0f4fb7ab96d8004999dda67a7b01869ae2e0243da07974a010b'),
(168,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 09:26:54.845276',NULL,'76474ffeec18212232156d304ed99939c6e404b500b7d32f8d34c2e10fa715ce','1c5ed8642cff11dba59891968e202344cef8a42be97493fb88de9d750c1a479b','f38f37d9d66f260ce4f9a938781921116aceba94fad7468115b219950f891bfe'),
(169,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 09:26:55.879100',NULL,'6981f4b9a8b1fda5cd660df985c8f0af12a5637e79574a632c1a50d2847f4b87','0b30e19623fbb9729d9fbfbd45e193dd04bdb79fef3ed1d385297cfa08587bbe','76474ffeec18212232156d304ed99939c6e404b500b7d32f8d34c2e10fa715ce'),
(170,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 09:27:09.982539',NULL,'c3fedaa1f9eb809e0f2e99b76c593d000b8d8fcbe01ea882053ffee4096bd3b3','f63a57e53053840fdb148424b8c5fa5b67d46699ea3fd986ac2180934665d63f','6981f4b9a8b1fda5cd660df985c8f0af12a5637e79574a632c1a50d2847f4b87'),
(171,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 09:27:11.934659',NULL,'5f452d42f11b6b28445dc02b2bc068be87e109d1d483fb23638687e64cf34cd3','2546b415a58fb94ad11602fbf8d9e12ebe2d69a3a67e31dd1499dfa3de4e3a4d','c3fedaa1f9eb809e0f2e99b76c593d000b8d8fcbe01ea882053ffee4096bd3b3'),
(172,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (1 records)','2026-07-26 09:27:14.135736',NULL,'8029375aa58571770861a7c115508875b19d6466cb201882560854f3c66217dd','481e95e8e885b641891b4da2d832cbe580b3a5e83d8ba65e623bb02dda1e1d2a','5f452d42f11b6b28445dc02b2bc068be87e109d1d483fb23638687e64cf34cd3'),
(173,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-26 09:27:14.578154',NULL,'d9ae7563b983570b577d7437595170ed12bb2a3eb481b9cd6e008e180d167890','dba59374418bfa7d1da7499fb38715783e012108049d583b96f45ccb2952a1c9','8029375aa58571770861a7c115508875b19d6466cb201882560854f3c66217dd'),
(174,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 09:27:32.834823',NULL,'e127da1bba3261fc857a2cfd6f085e4d3d42e5538e2ab1939308e5fe1ee2bbbc','581da883f93cb32b65e901508a7987055c1435b4918be9efb40d15cfb883be97','d9ae7563b983570b577d7437595170ed12bb2a3eb481b9cd6e008e180d167890'),
(175,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 09:27:34.259952',NULL,'5f3cd820a6ef78d2e70831f9f3386b7900f2b0f2818f95667c68eda15b8481be','1cc9e0ee9583c556a3e20865b3bace04b72dcfddc72bc6a5dbe4b98882a6ac06','e127da1bba3261fc857a2cfd6f085e4d3d42e5538e2ab1939308e5fe1ee2bbbc'),
(176,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (1 records)','2026-07-26 09:27:34.953865',NULL,'fe8b3780b6d6e7a965b8f7a4d985a0c2fc700612eed5771fcee206f6d103264f','c6b200be86206565b359989f7e3fc2541de647ee2b23203ee96d83f2fd749a1b','5f3cd820a6ef78d2e70831f9f3386b7900f2b0f2818f95667c68eda15b8481be'),
(177,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-26 09:27:35.068733',NULL,'96b99a77f1d7bc040cb8bff54c64be48f69f2b2bc564814e5d1b4a023b0afdf3','14f0c6557336c1eea49b1d168738396b570ee157777230fd4639d311ca205ce5','fe8b3780b6d6e7a965b8f7a4d985a0c2fc700612eed5771fcee206f6d103264f'),
(178,'member_registration_request',9,'TREASURER_VERIFIED',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1',NULL,'Treasurer verified registration request for JUSTIN VON T VERGARA','2026-07-26 09:31:20.753062',NULL,'52a1e16b3b72ce3573587115cde1edcbd2399c3b9f202920d80966a4d8640edd','ba2ba4b412092c14f809725da3a7f28feb2ddc00931e1772254a7359e2d6b122','96b99a77f1d7bc040cb8bff54c64be48f69f2b2bc564814e5d1b4a023b0afdf3'),
(179,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 09:33:03.036109',NULL,'fb5709b8efcc553d0268059a3a8df212db1c810898c15dddc1e6b1c245041643','ab969bbecea816f34506693068ad0c23ec653938c5a42d90fca7afba53fd97af','52a1e16b3b72ce3573587115cde1edcbd2399c3b9f202920d80966a4d8640edd'),
(180,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 09:33:04.683393',NULL,'ba2fa2ba4141b241333cf31759263f044d669a1c4874814998f4e853db5918b3','4faeb65d551a79fbdaace3289d2e10ff0b3b501b42c4b0113789324981389a68','fb5709b8efcc553d0268059a3a8df212db1c810898c15dddc1e6b1c245041643'),
(181,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (1 records)','2026-07-26 09:33:05.783143',NULL,'eac0c982091f2fc94017b3bc53b6d6aa23a0492672450daf814edc7edbbd5e15','bfa28a6da7d7b4e408626428ed0b315f1915963d115d406e0d5bb35d5609b758','ba2fa2ba4141b241333cf31759263f044d669a1c4874814998f4e853db5918b3'),
(182,'medical_aid',0,'READ',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-26 09:33:05.972856',NULL,'fec16e343fd060b995cef9c98c38fefbf0c3523778357d40e7ddc045a8ef5e95','b1906784d1f55366974cc14bac0b3810a120f552052ef9da2ead5e5f6f775292','eac0c982091f2fc94017b3bc53b6d6aa23a0492672450daf814edc7edbbd5e15'),
(183,'member_registration_request',9,'AUDITOR_VERIFIED',NULL,NULL,'Auditor',25,'FREDERICK MADAYAG','127.0.0.1',NULL,'Auditor verified registration request for JUSTIN VON T VERGARA','2026-07-26 09:33:42.637600',NULL,'2886b6241735effe4b0310b89752d98761475436e517ee9b5dc68191847b281c','0bfc1d09525443344c28fd50a66847bc982adb9c38f0335a86c91957c4483037','fec16e343fd060b995cef9c98c38fefbf0c3523778357d40e7ddc045a8ef5e95'),
(184,'member_registration_request',9,'PRESIDENT_APPROVED',NULL,'{\"member_id\": \"9\", \"officer_user_id\": \"35\", \"fee_id\": \"9\", \"status\": \"President Approved\"}','President',23,'President Account','127.0.0.1',NULL,'President approved registration for JUSTIN VON T VERGARA. Member/OfficerUser/MembershipFee created.','2026-07-26 09:34:41.356599',NULL,'d0e9431b18382a6d9ffa25dabe468f50107e7d10889480ccf5bb4deee2a5c1fd','4d0b4ca7b4eda8c5adee4ec1f5184004864ad5a08051a04bc1b0cdd14e2dc026','2886b6241735effe4b0310b89752d98761475436e517ee9b5dc68191847b281c'),
(185,'member_registration_request',10,'TREASURER_VERIFIED',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1',NULL,'Treasurer verified registration request for JOHN PAUL R VERSOZA','2026-07-26 09:41:30.692749',NULL,'e679e73cbe6177031906b396f7a47872289c75ac82db2882ba4c1ec1e8ad7f91','4f1721cb774bcfd42d85fb18937aface9bc19b70006107ecbac29a3e0af64a6e','d0e9431b18382a6d9ffa25dabe468f50107e7d10889480ccf5bb4deee2a5c1fd'),
(186,'member_registration_request',10,'AUDITOR_VERIFIED',NULL,NULL,'Auditor',25,'FREDERICK MADAYAG','127.0.0.1',NULL,'Auditor verified registration request for JOHN PAUL R VERSOZA','2026-07-26 09:42:44.968603',NULL,'02a68245cfdb135e942bd02a9148bdd8150fea876a37ca1158a3e6b3d24947f9','6105332d74e60d11029e7389c4e44a9587e092bd23d89cb278fe122027ddc940','e679e73cbe6177031906b396f7a47872289c75ac82db2882ba4c1ec1e8ad7f91'),
(187,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 09:43:22.677271',NULL,'b2859cdd3bea85f90a382a0945aef27b27837010da217bc83bf4961c4a736c4d','482a2bd6f6fbec899705a5ddf4569273da1f89c75cdeb785963cb9751fa9f4dc','02a68245cfdb135e942bd02a9148bdd8150fea876a37ca1158a3e6b3d24947f9'),
(188,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 09:43:22.842207',NULL,'ba24cd7e1f534b021a81c96fabf8bf5e15cf35b34e0989ddbaf04cc0b3072c74','1e77f4bbf6410333475137417da98fcc789bb82ef01339a6a23c41802223b7e7','b2859cdd3bea85f90a382a0945aef27b27837010da217bc83bf4961c4a736c4d'),
(189,'member_registration_request',10,'PRESIDENT_APPROVED',NULL,'{\"member_id\": \"10\", \"officer_user_id\": \"36\", \"fee_id\": \"10\", \"status\": \"President Approved\"}','President',23,'President Account','127.0.0.1',NULL,'President approved registration for JOHN PAUL R VERSOZA. Member/OfficerUser/MembershipFee created.','2026-07-26 09:43:41.987992',NULL,'01bc3867a4541d6015f2d6e33adc56bcb03b486a4433641c5de4055831fd3831','4648a393c555b5df395db9cd96259a29acb88d92b2a1378caaa4c1857c4d8f0e','ba24cd7e1f534b021a81c96fabf8bf5e15cf35b34e0989ddbaf04cc0b3072c74'),
(190,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 09:45:45.685844',NULL,'d66f6483d053660d3b87480c6e74061b2e41b1ef718d44ef5349e0ee4d04814a','03afb5f91567ba038e07b00253c01dbd61f072b314b5b9e228c50ff1ad9650e2','01bc3867a4541d6015f2d6e33adc56bcb03b486a4433641c5de4055831fd3831'),
(191,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 09:45:46.245711',NULL,'6107674883d4388079ee5e6123c55ecca769b18f92c6c19dab6a35f6046f0421','bd4af77aca4ac239a6a58a86210cf9e379d6051dc7d869a5e441f55c03a766f4','d66f6483d053660d3b87480c6e74061b2e41b1ef718d44ef5349e0ee4d04814a'),
(192,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 09:46:12.581865',NULL,'d4112d27d013a961f08e2517c67b071468ffde6a161fc857e79599d826cb02fd','85724135197888daefea527a590b4ec018db7ec01396b995c5e9c46355acf521','6107674883d4388079ee5e6123c55ecca769b18f92c6c19dab6a35f6046f0421'),
(193,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 09:46:13.344459',NULL,'0dde340f97633115f13ffa0125bdb9b10d7fbfe7d4c7ac30c4458c8dab4db58d','1c9dd762c70164fa823ca3f2e3c53dff16e7e1394862e07047a497c88ca8d602','d4112d27d013a961f08e2517c67b071468ffde6a161fc857e79599d826cb02fd'),
(194,'member_registration_request',11,'TREASURER_VERIFIED',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1',NULL,'Treasurer verified registration request for JUSTIN VON T VERGARA','2026-07-26 09:58:05.141662',NULL,'29ed5f19e68efea85a56fc9a825fbb0b2538062456471296804f1684daa33592','982964f737249a29e4847b94f9ecd64b2bab58fcb9bc9ca6d86441ab197f11d8','0dde340f97633115f13ffa0125bdb9b10d7fbfe7d4c7ac30c4458c8dab4db58d'),
(195,'member_registration_request',12,'TREASURER_VERIFIED',NULL,NULL,'Treasurer',24,'JASMINE ROTUGAL','127.0.0.1',NULL,'Treasurer verified registration request for JOHN PAUL R VERSOZA','2026-07-26 10:00:52.517817',NULL,'d792ff920092167b309a25c5d25d503e5baef02691b810f4b0fedb2797267dfa','f9c014cd265c3a00952365435046bf2fe7847e968e4fe6790fa4f2d9a6a0a9c7','29ed5f19e68efea85a56fc9a825fbb0b2538062456471296804f1684daa33592'),
(196,'member_registration_request',12,'AUDITOR_VERIFIED',NULL,NULL,'Auditor',25,'FREDERICK MADAYAG','127.0.0.1',NULL,'Auditor verified registration request for JOHN PAUL R VERSOZA','2026-07-26 10:01:42.630469',NULL,'bfadcb95f39d613e9e22d72bc1254a50a76e2cd30a9d41e4ba2de6b63ca4d8b6','f683f1df652fcc092073dceba1fe2c140153b2b7c5d0bc9a6cc31d50db433793','d792ff920092167b309a25c5d25d503e5baef02691b810f4b0fedb2797267dfa'),
(197,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:02:01.900437',NULL,'c3aa601ffab843ae6a89d144968ad913ab77bf60bf86326b2da3c03cfe15c960','f97ea4cef2cb226f14289786542998f3e19300a1313e4f7b64e3a4ec5cf9e3ed','bfadcb95f39d613e9e22d72bc1254a50a76e2cd30a9d41e4ba2de6b63ca4d8b6'),
(198,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:02:02.383682',NULL,'cf4a4078741a82d331227245e42fe9c56835fb74f1d66d6f3a97c5089973b327','e557e70d512af1687313100818f88208c876db1a1b84da71b848b5650ac0cad1','c3aa601ffab843ae6a89d144968ad913ab77bf60bf86326b2da3c03cfe15c960'),
(199,'member_registration_request',12,'PRESIDENT_APPROVED',NULL,'{\"member_id\": \"11\", \"officer_user_id\": \"37\", \"fee_id\": \"11\", \"status\": \"President Approved\"}','President',23,'President Account','127.0.0.1',NULL,'President approved registration for JOHN PAUL R VERSOZA. Member/OfficerUser/MembershipFee created.','2026-07-26 10:02:25.823038',NULL,'03f92e66d2a2dc013615cf9f9a41b8b488b418c0ceaa4c0bd40f0cb98c633a25','7489c09bba9758fd1a730081537e080ace75582f0a21a94db48e9a770b618ac4','cf4a4078741a82d331227245e42fe9c56835fb74f1d66d6f3a97c5089973b327'),
(200,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:06:16.940586',NULL,'97fb4c9e768bb1e4f8d8401a6d9ac4b623b667125ac828e1d29a0b56723e1121','54038ee6232e3e0500e900a482f0a92930702fd178c20b11dbd7e3c33b875ecb','03f92e66d2a2dc013615cf9f9a41b8b488b418c0ceaa4c0bd40f0cb98c633a25'),
(201,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:06:17.460437',NULL,'37838c54a1e0ce39521e267c8aac80ed6ad405f692d70ad96b79ba6c06c37dec','6e313800aea20fb14ad4af47acf3bc71e77be3c76ccb0c2db122ad34967ddd6b','97fb4c9e768bb1e4f8d8401a6d9ac4b623b667125ac828e1d29a0b56723e1121'),
(202,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:06:34.091137',NULL,'f318f0d8ec67e0202afeb8eb8944265cf1210e2d6f3c48fffca3d30d906d15eb','70babaa75da6e936d167be247cda089810cddc25cf139a1710316b1d93adb160','37838c54a1e0ce39521e267c8aac80ed6ad405f692d70ad96b79ba6c06c37dec'),
(203,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:06:34.963774',NULL,'652033e5379894fe982e3b07cfb157c818b2364d7bfa0eb354e1d03f0c6bacd2','435547fac0d9b189a766621639deadc68dd773979f2f193156d83c5eef39859d','f318f0d8ec67e0202afeb8eb8944265cf1210e2d6f3c48fffca3d30d906d15eb'),
(204,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:07:11.489099',NULL,'40aef9f5e58cbf3aa67d2e6c39a945ad7120c835420db889e5d5a3cac8d354f8','6fbc85223a51932e2af693c57de57ee190c92467372350e896b6a85555913e63','652033e5379894fe982e3b07cfb157c818b2364d7bfa0eb354e1d03f0c6bacd2'),
(205,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:07:12.300986',NULL,'b402c2124a45cb7e7ae2d6b834a0098a75ac2b43be152d629adbcf7187bd2c49','2f8f39fdd7d431421ef3c39f73cf0fbb62df573276a202533fb801c31dec9c04','40aef9f5e58cbf3aa67d2e6c39a945ad7120c835420db889e5d5a3cac8d354f8'),
(206,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:09:38.218809',NULL,'acf56b7aef72433ec890f00903b852835835d2ab99eb646167fec82708ec78dc','91fed59a40d026e0d3703e46c7a88febefb113cd61821a4f003b065b98d4a7b8','b402c2124a45cb7e7ae2d6b834a0098a75ac2b43be152d629adbcf7187bd2c49'),
(207,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:09:39.078598',NULL,'c3a07ab1799eab7fff7499217fea6a8f2555321ffcf72016f2a9be2a57b4253b','9a5741048ce57bb0ff7df605017ec782b68c2619f82088d5396af17ed889370a','acf56b7aef72433ec890f00903b852835835d2ab99eb646167fec82708ec78dc'),
(208,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:11:58.901111',NULL,'67011256306a9c3cbf820146ac8e97cc633a011e55077a4afb068f0a0cc6fef5','58211c5de94a5e867fea2fa97a7bf183691dc7f4222155c82747658d1c999586','c3a07ab1799eab7fff7499217fea6a8f2555321ffcf72016f2a9be2a57b4253b'),
(209,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:11:59.323412',NULL,'135bd8be9b65a2e73d147b0b31832d4232662d0f23f038ca373b301af2db6bec','85b6db77cbd068610194539be46422fba83df94b3334e57345cd7f237fb1b9e2','67011256306a9c3cbf820146ac8e97cc633a011e55077a4afb068f0a0cc6fef5'),
(210,'member_registration_request',11,'AUDITOR_VERIFIED',NULL,NULL,'Auditor',25,'FREDERICK MADAYAG','127.0.0.1',NULL,'Auditor verified registration request for JUSTIN VON T VERGARA','2026-07-26 10:12:10.428124',NULL,'3b15d1efbcad582adbe0a67e41127c53d148051a44f2a8c647d13997ec983cb3','0b421d1778f142648d7d7c3b0c72615a0626246185578053b5672fbb0edf5137','135bd8be9b65a2e73d147b0b31832d4232662d0f23f038ca373b301af2db6bec'),
(211,'member_registration_request',11,'PRESIDENT_APPROVED',NULL,'{\"member_id\": \"12\", \"officer_user_id\": \"38\", \"fee_id\": \"12\", \"status\": \"President Approved\"}','President',23,'President Account','127.0.0.1',NULL,'President approved registration for JUSTIN VON T VERGARA. Member/OfficerUser/MembershipFee created.','2026-07-26 10:12:49.297887',NULL,'29915aeedec5b71bdf8b92a9bf655c13ef90003321b39dcd5e5f9bcb3477080f','d9fee565345f553a593e791e26c358fc72521e222496f2205e22a971bac96403','3b15d1efbcad582adbe0a67e41127c53d148051a44f2a8c647d13997ec983cb3'),
(212,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:17:53.334389',NULL,'1239b83cb55476868af7aae92b49fa766fca8cb88c42d7e4550f5baf20e56aa0','81fcfd92f6cc580f307e2d8b4acfc7c2e0e87f63d06a431080e3a8d64bdac7d3','29915aeedec5b71bdf8b92a9bf655c13ef90003321b39dcd5e5f9bcb3477080f'),
(213,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:17:54.092570',NULL,'dc5164db2662b0fd9827e4a1e664aea461bb81b0af527bc7cce3131445e00612','010cf67321763c87010a51a7d44c13911e989fc9810c2475d158ff7123185806','1239b83cb55476868af7aae92b49fa766fca8cb88c42d7e4550f5baf20e56aa0'),
(214,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:21:45.440520',NULL,'962a4bdbb4c4ea132a9ed33616a7db35c5183f444b5bbae863c2bb8d79bbd4b7','dce59b6538178c9bd464271e4cd550d6a78a5a95b058dfa14f9cf99e93299321','dc5164db2662b0fd9827e4a1e664aea461bb81b0af527bc7cce3131445e00612'),
(215,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:21:46.577022',NULL,'62caa456c9a90e05e0ae218124da1e8d8635c516376b9882c544f413031460be','d8400057cea2b91492608498e0ec2da5270325a27db0d6e25aa334a0b192ff4d','962a4bdbb4c4ea132a9ed33616a7db35c5183f444b5bbae863c2bb8d79bbd4b7'),
(216,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:22:15.662084',NULL,'b3b498c2c0e93aabf6f4de9dd67ca09af92d9d7fa047971791a3a4de95084302','7b72bdf3dfd38c730d44493d2a146cb91ce23849313c1c10ed043026d507a582','62caa456c9a90e05e0ae218124da1e8d8635c516376b9882c544f413031460be'),
(217,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:22:16.133694',NULL,'137a44e28221884bbcffeec26073f909720d72ae1636afc915a33eea5103b24c','38dab5c294f675963d2fe25c260ae89451cc6c6eb7b207981b55c53280807a3d','b3b498c2c0e93aabf6f4de9dd67ca09af92d9d7fa047971791a3a4de95084302'),
(218,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:23:15.713725',NULL,'33366374adb45cc88de5612543da1135f92cffd07381b35b00eacfc1b0ff9778','b1a4f91d4c6139c9c779441021be4aff0c03b96c986e1ab939de4afd8f967877','137a44e28221884bbcffeec26073f909720d72ae1636afc915a33eea5103b24c'),
(219,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:23:17.179932',NULL,'ab04387b37d7ffb161a12c63f2d902c402931a318a8e4a03685d793cdc278fe3','cd72a7174cd033fec35bd1ecf88dbc775ddefcbb241425f86355d5cc6d14fb66','33366374adb45cc88de5612543da1135f92cffd07381b35b00eacfc1b0ff9778'),
(220,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:26:19.006735',NULL,'edff2c2cc86869be372fdb5aa78a3bcaceff38456e959c75f47b486e3c8ad5d0','2b6508fbcd78ef894b71fadedc34f16092ccb897022f43e8e615fe029b395c1e','ab04387b37d7ffb161a12c63f2d902c402931a318a8e4a03685d793cdc278fe3'),
(221,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:26:21.230358',NULL,'ab7fce1c96af0d81c5a37fe15ca3cd4105db7ff4f31e65aa9cac010aab1ae3f7','6ad439c11845ee2c1ff7db3dce309fa93d7973c0c4e9eb57f3080e60d7f6889b','edff2c2cc86869be372fdb5aa78a3bcaceff38456e959c75f47b486e3c8ad5d0'),
(222,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:26:44.107317',NULL,'7a188851c068993cdc89322ff9978862c926e6bea6a337cdde8da6e80a55e460','f7ba14ed300be376b1599d8e8d7e693de648cbb18bbc99fb0413ce6768bfcb7f','ab7fce1c96af0d81c5a37fe15ca3cd4105db7ff4f31e65aa9cac010aab1ae3f7'),
(223,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:26:47.900649',NULL,'7e91473134dc2518d60dc761c059c40ea144a6926547b737f51fe8d377508e6c','061934114758c961529b2250e187108189ff7eca1839722312927fb839d53541','7a188851c068993cdc89322ff9978862c926e6bea6a337cdde8da6e80a55e460'),
(224,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:27:07.180356',NULL,'b1202c2c9bcc102a61f74d10a445ef09f9206e65c0c9a5478049f351ba25519a','acc328846852276782bc88e92c67f8c4008a4e8557438a1a71899450e1db615e','7e91473134dc2518d60dc761c059c40ea144a6926547b737f51fe8d377508e6c'),
(225,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:27:07.470904',NULL,'22e21819bea6b8fa1e4777d78267c06b55952ec16f6fd71b13a3c557b5c64814','d55e17c2b9f53d84c8b8f80e8471e3a9a010a35c66246c50f77b8c11c16ae81b','b1202c2c9bcc102a61f74d10a445ef09f9206e65c0c9a5478049f351ba25519a'),
(226,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:27:22.819229',NULL,'45a963f56eef636109f6a4d7cb4d1ea4c6f89473fe9067106604ff5d67ed9945','7d4c7a940e8e38b0e4329cc04a5322e50da8efe79af6dc013c792a7a4262187c','22e21819bea6b8fa1e4777d78267c06b55952ec16f6fd71b13a3c557b5c64814'),
(227,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:27:23.588794',NULL,'fc773a71e1dbd1098288083cba855a3db75bffcf7931f6ce35d1fb0cbeae5817','098eba3c9433e6f69048348e2cd93d0a37022f0647054c7caeaf70c8c7eb7dcb','45a963f56eef636109f6a4d7cb4d1ea4c6f89473fe9067106604ff5d67ed9945'),
(228,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:27:48.197101',NULL,'94d9625949d0c836162254cab4d73d929409fc8f434e8e33907a22af4868434d','678cca9de4ceb0fe8319f76a8c16463ed09c964fc840d1815dd63d99d5377303','fc773a71e1dbd1098288083cba855a3db75bffcf7931f6ce35d1fb0cbeae5817'),
(229,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:27:48.673920',NULL,'ec60e9f9fee0029f2ef880dfc704b0184fce9cdf7a83aa5d191f282ac57d5390','5184ffb3afe1f01cd15c5f8e74cfe253c15a3acdfb2fa085a86f6a0be5b63137','94d9625949d0c836162254cab4d73d929409fc8f434e8e33907a22af4868434d'),
(230,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:28:31.824923',NULL,'c1e4b3747a6206041b9acf8bf5eeb78b1a5cf323edb3f2a8334019b2bb4a8000','85a33a4f8fb60d953fa17f78574dbf5cd79cf3f23cfa8f9f1247aea147cda1e4','ec60e9f9fee0029f2ef880dfc704b0184fce9cdf7a83aa5d191f282ac57d5390'),
(231,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:28:32.552447',NULL,'d708658f9633d5c6336a263ce5e9f8148980cce49eebcdac74130621912906eb','e7c11a061f2c416ac1e9b2d73692d92abdd754ef5c5e76a2b8693d1ddc381ea5','c1e4b3747a6206041b9acf8bf5eeb78b1a5cf323edb3f2a8334019b2bb4a8000'),
(232,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:32:34.884293',NULL,'d91022d77ae6c0e160d38e0124fcbe9671ffe0a9fa73f8c7b35dafcdaab12d01','8a9c4409fb654cfbf8ffa5617a21fcc790cc8c5aeb7decd41a160f21945929bc','d708658f9633d5c6336a263ce5e9f8148980cce49eebcdac74130621912906eb'),
(233,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:32:35.354236',NULL,'6874c7373a78bc33d29a9c7669bc5d80e636debaa5cf2d163ba1523bd34f4bfa','e399aa435b069a6b6305aff47eba32f63792d63d9ee6059436f3dc9919c34f08','d91022d77ae6c0e160d38e0124fcbe9671ffe0a9fa73f8c7b35dafcdaab12d01'),
(234,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:33:56.912390',NULL,'7711086d648dd67e14b074d1c9a9be89200abbae5186882826c6d82b691c0477','02e877c87d2e02515e4d0077e13547a46f82b5e2a449295c1f6d30bae126c571','6874c7373a78bc33d29a9c7669bc5d80e636debaa5cf2d163ba1523bd34f4bfa'),
(235,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:33:57.602995',NULL,'47eacef3ab8b57424b72ae05355411ceccf65b1b74fa70f960784310f9eb82c6','6101f3acf689e62f21d6ceba6b1183bedee8721b795126c6f24c7760ffcbf8ef','7711086d648dd67e14b074d1c9a9be89200abbae5186882826c6d82b691c0477'),
(236,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:34:12.921609',NULL,'b6cc64d8861b4369ba662586154c73972f601373b757e11df8cedc61cee06eea','4a01d8c126550de3f74bdbd3c88955fee78e5f6860d237f8c168322d021526db','47eacef3ab8b57424b72ae05355411ceccf65b1b74fa70f960784310f9eb82c6'),
(237,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:34:14.159925',NULL,'4ea81daadbf3e98d00d7bd96519162c318368debc227076a63855e12b5d2c32d','3adce1e84e22f5298bf5b220d57c1c51b28bf93cc6caf23a6394d305defdee98','b6cc64d8861b4369ba662586154c73972f601373b757e11df8cedc61cee06eea'),
(238,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:34:38.167713',NULL,'f0c3eb7fc6c9ccd4958b27f686b8246bba34de37c0e781a99570a39c60e099bb','6fe7f6853ef4d70b6459f5092c231821f7e8ac6e87bc25593860d3aa5e53b111','4ea81daadbf3e98d00d7bd96519162c318368debc227076a63855e12b5d2c32d'),
(239,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:34:38.864498',NULL,'441137127328c60bde90981600bc91f874305cb5d3206c7cfc26e66f966c0bca','7864e200826492a11baf99089dfb92f25bafdd53e564226be1e1354985104d8f','f0c3eb7fc6c9ccd4958b27f686b8246bba34de37c0e781a99570a39c60e099bb'),
(240,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:36:53.608256',NULL,'5f7edbe0df93ac4bb6b29e9ed31b321d443e56deb9534dfb2dd6a0d9deecaa0c','3ff833a66eab6dc916af0f87f76bc464d66510456de045f2ca69dee9b7c20fdd','441137127328c60bde90981600bc91f874305cb5d3206c7cfc26e66f966c0bca'),
(241,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:36:54.946088',NULL,'12897c88d35ceb6851ad8591e416e7d55e9bab59907029fc45b5f7819c8c10cb','be36628a278da0ba9ea773eee1cc9177da5db0bc12607310e258958cb7660d6a','5f7edbe0df93ac4bb6b29e9ed31b321d443e56deb9534dfb2dd6a0d9deecaa0c'),
(242,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:37:44.160880',NULL,'42ab5465fa19009b0e8fcbbc11cdebf340b5858c6a629b0a457fa35ab34fa671','6a1d911287861c149ac7935dbf203a18a664b4bcf8c28e1d543acb8aa91f4355','12897c88d35ceb6851ad8591e416e7d55e9bab59907029fc45b5f7819c8c10cb'),
(243,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:37:44.665305',NULL,'8a5884f955c1aa4aac6ed3f792df026389f91ceff3c8864515aefc2bd808df39','b702a581e599d94f04c8179b1dfc58e5fbf6eff7d581007d96b912ad6a4acc24','42ab5465fa19009b0e8fcbbc11cdebf340b5858c6a629b0a457fa35ab34fa671'),
(244,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:39:19.910469',NULL,'2fbac0a8f70f987831fa99bdb04e80a97c2b2b3950bf8ed658fa2ce299b5b1c9','cdad6bb7efa15f99ef2b14470f54566bb5ec08c66fd7e70e7bc8aaa19478a79c','8a5884f955c1aa4aac6ed3f792df026389f91ceff3c8864515aefc2bd808df39'),
(245,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:39:20.942124',NULL,'0a8556b03c6abd29950ff3ed1cac9b9782421bfab8f275164c0012d32946f0a6','882dbfa2624c5c3d04aae83f1054329bbf6d610ba5c1e84163d244b8c6d2440d','2fbac0a8f70f987831fa99bdb04e80a97c2b2b3950bf8ed658fa2ce299b5b1c9'),
(246,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:39:47.826640',NULL,'4573ee815a58a57c00b5797b8dff28973885cf0279276a1774a1eb07810f226c','41766c5d94668d515d83b24ce40f848037571e9543c31a15409972ae04725042','0a8556b03c6abd29950ff3ed1cac9b9782421bfab8f275164c0012d32946f0a6'),
(247,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:39:48.616643',NULL,'01a9e02d2826b05966f2339e6a68cf3391bd38846728ced2d81e10d5c2b76e1c','35932156de2b54d395a4cbcb3b711568008662513a27f1a66e7255eca2b7d2ac','4573ee815a58a57c00b5797b8dff28973885cf0279276a1774a1eb07810f226c'),
(248,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:40:26.203986',NULL,'59b130db35366151d2c3736b010dc28c6cced357b8bdf3e40f3d9b9725b55bad','f1231dc5508677632a248a904000cb37e2bdbf05267183572ea5ae9381f095a8','01a9e02d2826b05966f2339e6a68cf3391bd38846728ced2d81e10d5c2b76e1c'),
(249,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:40:26.955477',NULL,'3bb5e8197e8f822fd0e142fc1ddec2a03eec513d897862178827962e71aa1cb8','fded207c59cd815ee4256421af57a113f4e3309780a66c6fe4f216a11dbdc737','59b130db35366151d2c3736b010dc28c6cced357b8bdf3e40f3d9b9725b55bad'),
(250,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:41:05.754500',NULL,'c6783a808b48b375439ca15fcae49a1be613b01a8ddf77c7bb4710b3c0e33338','79f9794194835b68b62668fb9cf758d21d4f5e30dcf4361e371ea73e3f963578','3bb5e8197e8f822fd0e142fc1ddec2a03eec513d897862178827962e71aa1cb8'),
(251,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:41:06.426444',NULL,'1fefb61f4967dcfd2e4071fc7573468be13c1a08604b04bba5dde492113b60ae','f61c9eeb6cff81959c13c566952756d1638f9294eb2845cf2861fbf09b610cf3','c6783a808b48b375439ca15fcae49a1be613b01a8ddf77c7bb4710b3c0e33338'),
(252,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:43:13.838814',NULL,'f3f602d26b8d543b688e4bad4f8a617ca904b16e9e12ba0569fc3b0c45a1ba03','895b2a2c3aa0236e6b4ccc5b97f17a22b6681d2cf4cb95f95e4c29a93fd04a8a','1fefb61f4967dcfd2e4071fc7573468be13c1a08604b04bba5dde492113b60ae'),
(253,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:43:14.351040',NULL,'624e8d4dd54809f90a0a0e40923f3bf2a4d00ae507ff06dd71de8c273ec1520e','1ec5cb2d4877e743c0492a003af754a8a2c62ba022e9f701562f39e56c325353','f3f602d26b8d543b688e4bad4f8a617ca904b16e9e12ba0569fc3b0c45a1ba03'),
(254,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:43:41.654000',NULL,'8b83798b29ff0d436ce303c0b27234a3f33621aec031ad86c38b407814a2b771','98bbd94b371b510b09c5a7bb943eb7b2087c2688edaaca2873112d687298cc25','624e8d4dd54809f90a0a0e40923f3bf2a4d00ae507ff06dd71de8c273ec1520e'),
(255,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:43:42.243046',NULL,'5bce89f107a26366b1ce52094c63b5d83cc6eb7b5bc08b84ebacc515fe80b0de','2f9d178487c0b0cf63d652ab0c5aa2be607dca182c99ca26ba0046aa029a678e','8b83798b29ff0d436ce303c0b27234a3f33621aec031ad86c38b407814a2b771'),
(256,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:44:23.786095',NULL,'8017df4a3a871db1bd34f5b0dc997967629268f62e51d4f171b0041c260a93d0','27d5cb377cc9e703e371c8f8c9b86294ba1f5123ac2c119dd3cee6d7c4e105ce','5bce89f107a26366b1ce52094c63b5d83cc6eb7b5bc08b84ebacc515fe80b0de'),
(257,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:44:24.418483',NULL,'d963de5b3c1f582bb2e5b43abae1fda0a351315341e4f4d0335cac328dd7414a','a6b873ad79e2ae3efa021fb6b5c81c30e3c33dc29f71b98faa3b506566d934e1','8017df4a3a871db1bd34f5b0dc997967629268f62e51d4f171b0041c260a93d0'),
(258,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:45:45.808455',NULL,'cef2e7d44c9357df5a7632b2a64877c6016549bf82f19b6c74fcfbf5ca442c92','d3506a9cbcf26f3c887f2c03f81e21119457c8b6093e066bf461f4b2b879c188','d963de5b3c1f582bb2e5b43abae1fda0a351315341e4f4d0335cac328dd7414a'),
(259,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:45:46.441906',NULL,'7edf51365377beba62e8f421df02bffd306cbcfb8e2dace7d39e1bd4e7e08735','18521ffcf5e9d8e58ecad63fd247488323656ee0b5d5494b6d2570153bb31c8b','cef2e7d44c9357df5a7632b2a64877c6016549bf82f19b6c74fcfbf5ca442c92'),
(260,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:47:10.000350',NULL,'c272f3266f3f4661827c0cd796e9720eaae953f2a914d809c36ed741dce4cb2b','ea245db33c43f7efa98459ba33e3b0dd8e5d90c4f59493eb56759f5a8e0ecdcf','7edf51365377beba62e8f421df02bffd306cbcfb8e2dace7d39e1bd4e7e08735'),
(261,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:47:10.375295',NULL,'d1393f1897a51b2e3c98cc95a97d5cb2d8f69666c5b5843272951cfc1f683354','278f0cdd65a2bb76ae5a2c1721b99fbe0c758d5eb914c987294c87d0672bf287','c272f3266f3f4661827c0cd796e9720eaae953f2a914d809c36ed741dce4cb2b'),
(262,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:47:27.958212',NULL,'6ed44f8a4f001cf6d32cb4827c6c7227909af2bc10061749a735db3984760122','bf9e26077d439dac7645188b421db4d55d2e6406e8bcaf6d931691821231996c','d1393f1897a51b2e3c98cc95a97d5cb2d8f69666c5b5843272951cfc1f683354'),
(263,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:47:28.253528',NULL,'e480178eaf89f324fd57e95c8b02f7912a11fb33a18c36ea5256fb3dad625dcd','48dedc658588f49b8e4019e7309210e3a7cd68133aa7c7073039bc2c5d5c100a','6ed44f8a4f001cf6d32cb4827c6c7227909af2bc10061749a735db3984760122'),
(264,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:49:23.789898',NULL,'16ea0b2411667da7181854562ea7c1b98376ccdd4d0bc5fa59492f5352e4ba3b','8f400edcee9b4b1078a028021d3d5fca42a4d9f99886eef7e6af1978392382c1','e480178eaf89f324fd57e95c8b02f7912a11fb33a18c36ea5256fb3dad625dcd'),
(265,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:49:24.310253',NULL,'605b520820c39cf3b9e2934608b89dde924b4b9c91f955931886d94b7fc6d338','53a40c2df7221c091248714510c6821790dc0a0f110402de899fbc82fc31ab13','16ea0b2411667da7181854562ea7c1b98376ccdd4d0bc5fa59492f5352e4ba3b'),
(266,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:49:45.905391',NULL,'57949d7b50ad1d38d1125454670aee538e11d2bc87202b55bfda9123816c117c','b235d93409128c7ddd96f2b5791b56138e40b8bb0a9f329b82a74f20d60dc822','605b520820c39cf3b9e2934608b89dde924b4b9c91f955931886d94b7fc6d338'),
(267,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:49:46.489854',NULL,'2df622527200119b55b9bd290895743c3d15376fcdb549a802e4b02b8f5025f7','0ece95b6ccc12dd95fda20c230ea2f0069d749726bdf2164177bed5aca633685','57949d7b50ad1d38d1125454670aee538e11d2bc87202b55bfda9123816c117c'),
(268,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:50:09.159604',NULL,'aaaddcbc11a85687d373a88d7a2575f03be294c9a3b1936def479e77a97c3087','c02ac55c9ead85bf3e91dd235684a29bd6ed3892da888dbc70256efebbaecbc9','2df622527200119b55b9bd290895743c3d15376fcdb549a802e4b02b8f5025f7'),
(269,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:50:09.327930',NULL,'c66bfcfb62059e9e149cc858a7b13ab5b69b66bdc05dae80fb369ebb99ded1af','6194b8ebc6eb04996729698fe0a9552eba22d32cd7f7df925051d2932587795c','aaaddcbc11a85687d373a88d7a2575f03be294c9a3b1936def479e77a97c3087'),
(270,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:50:37.025114',NULL,'61e8b4e0457c5f2e9fad7bdfad2797d9ad1af0dd9b47b378248e218870d7c4c6','6f8d8b5691910d31890e718f723b559faa5177e948eacd06e3d45877b0d12cea','c66bfcfb62059e9e149cc858a7b13ab5b69b66bdc05dae80fb369ebb99ded1af'),
(271,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:50:38.029699',NULL,'eca85bd71b5f310264dd87cafd0e5997daa68d75e7256640562f94707c740682','abdbedcdb7942190dd95ad06ecd84c4ceed891aad68238236960b7063a7237da','61e8b4e0457c5f2e9fad7bdfad2797d9ad1af0dd9b47b378248e218870d7c4c6'),
(272,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:50:59.791799',NULL,'6e7f106d368066fe0488b90119bd2a7ada3b7a15227eb0fcb67da77b22e0bebb','2e7e1f5cb00f552515cb8ab9aa400acf890a726092733ed5ead4b8500eff29b7','eca85bd71b5f310264dd87cafd0e5997daa68d75e7256640562f94707c740682'),
(273,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:51:00.078647',NULL,'69a7fc610536fcf8ac07f876c3192e39bbfcf62866a9403f90d453ba486e0fdb','6ff39d9616408d26da8917a95dd499bda81a6b9c6fa59705516c7d8edf394479','6e7f106d368066fe0488b90119bd2a7ada3b7a15227eb0fcb67da77b22e0bebb'),
(274,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:51:21.481222',NULL,'09890b9fe9522f7be3e6f1d1665935a5ae152c66db4093bd4719ecd594334f42','c6ce6d7a999ac4d8fe66ea22fd233e597d70b7911a396bf96cc292a296712afd','69a7fc610536fcf8ac07f876c3192e39bbfcf62866a9403f90d453ba486e0fdb'),
(275,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:51:22.074023',NULL,'2b170131eb7c9cef82535083461d89688edfb9ddf2f5b3ab5f914b5018fc6822','b8afede85ef14393753daba9f2d8ce58ffc3c7c3d5b96fd07d351acbe66e3095','09890b9fe9522f7be3e6f1d1665935a5ae152c66db4093bd4719ecd594334f42'),
(276,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:53:25.438705',NULL,'155b6fd458047d20fd4ceedf9db92f84420acc4aa9e432db13f1b828303643f1','8c4087caa22806071f30371e81cbc4039c35737416591d9d961bbb8658f2f45e','2b170131eb7c9cef82535083461d89688edfb9ddf2f5b3ab5f914b5018fc6822'),
(277,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:53:31.841191',NULL,'edba2e711a68fc395e129c995db925b59e33aedcb9b4398dfda40984b9d95a49','235fec60cc87a9a597adde5daa91667f611afbc857d764ac35c0de7766137c8c','155b6fd458047d20fd4ceedf9db92f84420acc4aa9e432db13f1b828303643f1'),
(278,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:54:04.232356',NULL,'64c19e225ab44912a99f3ec96f8dbb2b638dd2bd34bbcca7dc02d9984daa366b','a4c30626d48c82bce31e71aad3b6892fb9f252713637c5bcfa050c1f2ddf4445','edba2e711a68fc395e129c995db925b59e33aedcb9b4398dfda40984b9d95a49'),
(279,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:54:04.741705',NULL,'cd2de9d7ff17d9d19d09865e64b8e5e7e5156e7399d19f0cd675c3b286a44ea2','2d9354a907bddf5a841f70128c313a40a9c454df05d20ebdec281d5b7f2c0017','64c19e225ab44912a99f3ec96f8dbb2b638dd2bd34bbcca7dc02d9984daa366b'),
(280,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:55:14.408571',NULL,'bf1324a1f296cd60c9ecb4245aae1b240e1c7c785e2f216d97db83231147cd47','109f55ef878075ce83b3de7a48d57a4d94fb584e51bac8d71b23d4075a9eab84','cd2de9d7ff17d9d19d09865e64b8e5e7e5156e7399d19f0cd675c3b286a44ea2'),
(281,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:55:15.478807',NULL,'1f8d2d3493464a6fa7e6f1598613427f767aab0fcfe78ac21bc5f34e5aa8b5fb','0bb6ae5ba3064f9f05c27bb93d1621f112a09376d1774a950521439de44ac453','bf1324a1f296cd60c9ecb4245aae1b240e1c7c785e2f216d97db83231147cd47'),
(282,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:57:21.945714',NULL,'587fac3efc75cc7fde91ea211203127ff44c39118a90d1b1d915a84ab6e1362b','8f461950f6c27a8d0f63f49891a8d3d6852c3b6b2e8103116c3dfbbb85894163','1f8d2d3493464a6fa7e6f1598613427f767aab0fcfe78ac21bc5f34e5aa8b5fb'),
(283,'medical_aid',0,'READ',NULL,NULL,'President',23,'President Account','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','President viewed auditor-approved medical aid queue (1 records)','2026-07-26 10:57:23.137439',NULL,'962acc1240d306bff54c37cf84dd8765a4199a10ca3cafdb1399c187698b9bbd','50a4ef08df3995b0c38c8d2bd1acb6750ad986115ed9d736fbeeee04c23bc1c3','587fac3efc75cc7fde91ea211203127ff44c39118a90d1b1d915a84ab6e1362b'),
(284,'officer_user',42,'CREATED',NULL,'{\"id\": \"42\", \"full_name\": \"FREDERICK MADAYAG\", \"username\": \"treasurer\", \"email\": \"vdark699@gmail.com\", \"role\": \"Treasurer\", \"account_status\": \"Active\", \"term_start\": \"2026-07-27\", \"term_end\": \"2026-12-01\", \"department_id\": null, \"department_name\": null, \"department_code\": null, \"mfa_enabled\": \"False\", \"created_at\": \"2026-07-27T11:47:21.836186+00:00\", \"updated_at\": \"2026-07-27T11:47:21.836186+00:00\"}','President',41,'President Account','127.0.0.1',NULL,'Created officer account for FREDERICK MADAYAG','2026-07-27 11:47:21.856582',NULL,'33ce82ce4884e407b0f4a8632ab63e1536b619a47ce844091feff71ca3b972af','d3517d5f5ca15d08dca9c5ae90b5350bbab128abf8697415335dca07f92dbf0e','962acc1240d306bff54c37cf84dd8765a4199a10ca3cafdb1399c187698b9bbd'),
(285,'officer_user',41,'UPDATED',NULL,'{\"id\": \"41\", \"full_name\": \"President Account\", \"username\": \"president\", \"email\": \"programmingproject06@gmail.com\", \"role\": \"President\", \"account_status\": \"Active\", \"term_start\": null, \"term_end\": null, \"department_id\": null, \"department_name\": null, \"department_code\": null, \"mfa_enabled\": \"False\", \"created_at\": \"2026-07-27T11:46:18.605147+00:00\", \"updated_at\": \"2026-07-27T11:47:35.072336+00:00\"}','President',41,'President Account','127.0.0.1',NULL,'Updated officer account for President Account','2026-07-27 11:47:35.077341',NULL,'a31fe20e015f5caa1a532e73626ab3e715e0a098c37c34a163ed1519ae7f7a98','e2e7b0bf1a65f50a2f7fce3928555d230ba08512287c85bb5c2763fb28f931a1','33ce82ce4884e407b0f4a8632ab63e1536b619a47ce844091feff71ca3b972af'),
(286,'officer_user',43,'CREATED',NULL,'{\"id\": \"43\", \"full_name\": \"RHOMAR MANARANG\", \"username\": \"auditor\", \"email\": \"vergarajustin636@gmail.com\", \"role\": \"Auditor\", \"account_status\": \"Active\", \"term_start\": \"2026-07-27\", \"term_end\": \"2026-12-01\", \"department_id\": null, \"department_name\": null, \"department_code\": null, \"mfa_enabled\": \"False\", \"created_at\": \"2026-07-27T11:48:14.191898+00:00\", \"updated_at\": \"2026-07-27T11:48:14.191898+00:00\"}','President',41,'President Account','127.0.0.1',NULL,'Created officer account for RHOMAR MANARANG','2026-07-27 11:48:14.197889',NULL,'7626dc4156906e21249a1ae31352839dd66fefa1dcaf1bd79e28dd3c2ab9e713','e9339189b3aa0bff37e70e2c908bf0f12fc3d8bd604dd02fc38459d7c50a1b0a','a31fe20e015f5caa1a532e73626ab3e715e0a098c37c34a163ed1519ae7f7a98'),
(287,'officer_user',44,'CREATED',NULL,'{\"id\": \"44\", \"full_name\": \"JASMINE ROTUGAL\", \"username\": \"secretary\", \"email\": \"jasmine.rotugal_cyn@isu.edu.ph\", \"role\": \"Secretary\", \"account_status\": \"Active\", \"term_start\": \"2026-07-27\", \"term_end\": \"2026-12-01\", \"department_id\": null, \"department_name\": null, \"department_code\": null, \"mfa_enabled\": \"False\", \"created_at\": \"2026-07-27T11:49:15.037630+00:00\", \"updated_at\": \"2026-07-27T11:49:15.037630+00:00\"}','President',41,'President Account','127.0.0.1',NULL,'Created officer account for JASMINE ROTUGAL','2026-07-27 11:49:15.042343',NULL,'9759d31a141e179e9e44623b13b443c7c8821107fedeaf055d2ac651581e823e','48308f985e40d8079ecf7744f025869823d97f5e6b717fa229040c3dbc1da9ba','7626dc4156906e21249a1ae31352839dd66fefa1dcaf1bd79e28dd3c2ab9e713'),
(288,'medical_aid',0,'READ',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (0 records)','2026-07-27 11:51:35.926936',NULL,'e7f14ff95ba4b499f202cc828f21014e0e063e4b21a1d2294c9f0a54e17aeee5','0e3f2628ec77669317196d817a69764ef67fb7d7cd283765f1ecec33d0f8815e','9759d31a141e179e9e44623b13b443c7c8821107fedeaf055d2ac651581e823e'),
(289,'medical_aid',0,'READ',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-27 11:51:36.002796',NULL,'8ae9545d6d7703fd5588193b943bd4c6ec4f2d892236d489435bb83ac49db040','a0e3d83c9ba414faf95df10c5d3b45b3df7684cc506439642e00faf3d27fcd94','e7f14ff95ba4b499f202cc828f21014e0e063e4b21a1d2294c9f0a54e17aeee5'),
(290,'member_registration_request',13,'TREASURER_VERIFIED',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1',NULL,'Treasurer verified registration request for JUSTIN VON T VERGARA','2026-07-27 11:51:45.925649',NULL,'3074b8d5c73e4be6c9ac828daa03fcacbf807b31b3c72b86c94c576709f65bf8','753ba7286e3d7e725098bbac2ea28a01bc800681489b0741d14835182ca7504f','8ae9545d6d7703fd5588193b943bd4c6ec4f2d892236d489435bb83ac49db040'),
(291,'officer_user',43,'UPDATED',NULL,'{\"id\": \"43\", \"full_name\": \"RHOMAR MANARANG\", \"username\": \"auditor\", \"email\": \"vergarajustin636@gmail.com\", \"role\": \"Auditor\", \"account_status\": \"Active\", \"term_start\": \"2026-07-27\", \"term_end\": \"2026-12-01\", \"department_id\": null, \"department_name\": null, \"department_code\": null, \"mfa_enabled\": \"False\", \"created_at\": \"2026-07-27T11:48:14.191898+00:00\", \"updated_at\": \"2026-07-27T11:52:27.226301+00:00\"}','President',41,'President Account','127.0.0.1',NULL,'Updated officer account for RHOMAR MANARANG','2026-07-27 11:52:27.237240',NULL,'c8162b6b5f821dde6e5b87c0be82ddef47329745d6cd0e32cd78acead76cb796','9f6faa5cbc6173a4827db904fcc95616098a2a044b07918eb4c5e1ae506aff32','3074b8d5c73e4be6c9ac828daa03fcacbf807b31b3c72b86c94c576709f65bf8'),
(292,'member_registration_request',13,'AUDITOR_VERIFIED',NULL,NULL,'Auditor',43,'RHOMAR MANARANG','127.0.0.1',NULL,'Auditor verified registration request for JUSTIN VON T VERGARA','2026-07-27 11:53:10.973411',NULL,'0c6a91cc37a1a02bde85742aa4999e8460ea4af7282957351f176ac2762daf86','7a17e4d61b7ab4ca155b2c3c31a7d201cc39d81b2c86358f4a1c91209acba242','c8162b6b5f821dde6e5b87c0be82ddef47329745d6cd0e32cd78acead76cb796'),
(293,'member_registration_request',13,'PRESIDENT_APPROVED',NULL,'{\"member_id\": \"13\", \"officer_user_id\": \"45\", \"fee_id\": \"13\", \"status\": \"President Approved\"}','President',41,'President Account','127.0.0.1',NULL,'President approved registration for JUSTIN VON T VERGARA. Member/OfficerUser/MembershipFee created.','2026-07-27 11:54:00.922974',NULL,'66d6cbd016bf2a410997841ba26970ed95d6ab38278c1f2eecb564b146ac6078','67080b5b0c3727a4b47fc12617f10fefddedc7789e4f818e2bb503e85245a21c','0c6a91cc37a1a02bde85742aa4999e8460ea4af7282957351f176ac2762daf86'),
(294,'medical_aid',0,'READ',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (0 records)','2026-07-27 11:57:40.341603',NULL,'965f615400f52d7c6352669ac9ec31a42ce9d65679961521506be461895f31e8','4b382734b65a5598a75d576ebaed0747c85c5beb69f94a56ae568c5b8dbc2d21','66d6cbd016bf2a410997841ba26970ed95d6ab38278c1f2eecb564b146ac6078'),
(295,'medical_aid',0,'READ',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-27 11:57:40.466349',NULL,'fa15aeb93a5ff350af752a2dee633781e5993217bcea7dad519d47d5d5bb1010','ecf1b39060294b2d8139b5cf7984d4ccd45889e5c2cbca6ecdb8b220459c6701','965f615400f52d7c6352669ac9ec31a42ce9d65679961521506be461895f31e8'),
(296,'member_registration_request',14,'TREASURER_VERIFIED',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1',NULL,'Treasurer verified registration request for TRISTAN R ILLARDE','2026-07-27 12:02:34.736390',NULL,'37e22c0279e73c42812a04e6a2d40652f7baff8e4bc059b791afaf87397afe37','9a67de473e5538a768a4b84773b84ea245f91c3e9aec9717636dd77c0f5ab8b1','fa15aeb93a5ff350af752a2dee633781e5993217bcea7dad519d47d5d5bb1010'),
(297,'member_registration_request',14,'AUDITOR_VERIFIED',NULL,NULL,'Auditor',43,'RHOMAR MANARANG','127.0.0.1',NULL,'Auditor verified registration request for TRISTAN R ILLARDE','2026-07-27 12:03:07.258824',NULL,'7ed0be770d6950762300aba0f11a81a97c34e806894828a28c2941c613b2e334','95055ac2c4302b12de0279ecd59e603e98688e7ae2686d7aab51f1fa71566649','37e22c0279e73c42812a04e6a2d40652f7baff8e4bc059b791afaf87397afe37'),
(298,'member_registration_request',14,'PRESIDENT_APPROVED',NULL,'{\"member_id\": \"14\", \"officer_user_id\": \"46\", \"fee_id\": \"14\", \"status\": \"President Approved\"}','President',41,'President Account','127.0.0.1',NULL,'President approved registration for TRISTAN R ILLARDE. Member/OfficerUser/MembershipFee created.','2026-07-27 12:03:49.282682',NULL,'51b1c21bb8d02b7dbbc916bc26dd8cb50dc4f9c0e790108268af919e33d4a732','b3e36505f70a9433c21eb2d75cc07613936ade99bd6ff7989c8c1af6847207bb','7ed0be770d6950762300aba0f11a81a97c34e806894828a28c2941c613b2e334'),
(299,'medical_aid',0,'READ',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (0 records)','2026-07-27 12:14:35.575854',NULL,'290c1182aaf4f0cb9e91de073e4d96332d3d4cf513e28d5509b7c832960d528d','33592953a2a86180ba255094a8704484ab144f35fd26de3bd0b928227e3cba79','51b1c21bb8d02b7dbbc916bc26dd8cb50dc4f9c0e790108268af919e33d4a732'),
(300,'medical_aid',0,'READ',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-27 12:14:38.998786',NULL,'38d5ad53f891450f2fd262a53eef67b3affc00d8b30fb19f26a3941e5702807d','e6a715616e9bc6022f3e25030c6323e03aa21a4a53a5b6c01fb2303889722f99','290c1182aaf4f0cb9e91de073e4d96332d3d4cf513e28d5509b7c832960d528d'),
(301,'medical_aid',0,'READ',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (0 records)','2026-07-27 12:16:04.693273',NULL,'07ddc0e91484d0c224eaa23126888c572bbd9daac76c9a3e47978c61d6f7a986','f4a3651f269b5388f53a2d4ede368da79e5018f69661f114db94013d77e8bc23','38d5ad53f891450f2fd262a53eef67b3affc00d8b30fb19f26a3941e5702807d'),
(302,'medical_aid',0,'READ',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-27 12:16:04.885243',NULL,'437e3d3b0deeab565f07274b41fa35af5c9a4ddf0752cf68f33138a183bb130c','5383e0c2026af118995331c48ffe4c0137c5fc579af7f59d43799c0caee7808e','07ddc0e91484d0c224eaa23126888c572bbd9daac76c9a3e47978c61d6f7a986'),
(303,'medical_aid',0,'READ',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (0 records)','2026-07-27 12:18:51.594721',NULL,'140adbe21458316974fd2826d7645ea2999544298662058ea0c94bf997389bc7','e7a08614468885d56f2baff62e0e68273f8e707598d2fbdc24cf60fecc49b27d','437e3d3b0deeab565f07274b41fa35af5c9a4ddf0752cf68f33138a183bb130c'),
(304,'medical_aid',0,'READ',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-27 12:18:51.847514',NULL,'94eb0a2a609b9fd98d597010d1d61a6dcb913106075c1765fe52861b66de2547','402de81d04d1c5153771493aa257cf8d58f14a35eaee9aa7e54035f035650287','140adbe21458316974fd2826d7645ea2999544298662058ea0c94bf997389bc7'),
(305,'medical_aid',0,'READ',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (0 records)','2026-07-27 12:19:27.878757',NULL,'67cd118a2d8061bdd69f8d609b4c996d4dfc7975faca59e2aea0662dd2718606','b78af9d594f8160cc128fbb79c31c8ae2a8eca77eb2e5cb0f2cc5bc42de1a3cf','94eb0a2a609b9fd98d597010d1d61a6dcb913106075c1765fe52861b66de2547'),
(306,'medical_aid',0,'READ',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-27 12:19:28.030828',NULL,'f2ad31a16d40bef4bc472f4ae9e65280ad01c81d299a8d35d25479afb0feae98','03b7d1101cddc094cedfde3e04afa8a51485ea2b330454da7da277c10c98de84','67cd118a2d8061bdd69f8d609b4c996d4dfc7975faca59e2aea0662dd2718606'),
(307,'medical_aid',0,'READ',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (0 records)','2026-07-27 12:23:18.297639',NULL,'8912ef2a418be845094ef9d414d1db3e6c1804e7e93ac3d02f343bfd6a832151','8577a0b6457c203a0afde1627428b8231f55b0ffde5490ea49bc49cc79bf2955','f2ad31a16d40bef4bc472f4ae9e65280ad01c81d299a8d35d25479afb0feae98'),
(308,'medical_aid',0,'READ',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-27 12:23:18.771018',NULL,'219c49064b16076c97c94e987607fd58934c15f69dd580aa3c4027a3bc517598','894cb6efe474a80f06a925827062976465290a71054b38e6e8cc36ceef079f9c','8912ef2a418be845094ef9d414d1db3e6c1804e7e93ac3d02f343bfd6a832151'),
(309,'medical_aid',0,'READ',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (0 records)','2026-07-27 12:25:23.263909',NULL,'d5fa573ed441b28dce4b2bad31c43fcf1f04d1f2c59c9203db629d16d9d29b90','d601914feb0bf57c4e950cdfdd1e7b891937436765411ea43bdb4852e7bc6b19','219c49064b16076c97c94e987607fd58934c15f69dd580aa3c4027a3bc517598'),
(310,'medical_aid',0,'READ',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-27 12:25:25.293909',NULL,'aaac407dfbd73c411f7fa1c2008e85963a3fd06e9afafa72136b14b5a1e3d8ec','206d352a5b593891b73ec684fb0921415e2f79494af76570e3b9cfc9e5b5e6a3','d5fa573ed441b28dce4b2bad31c43fcf1f04d1f2c59c9203db629d16d9d29b90'),
(311,'medical_aid',0,'READ',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (0 records)','2026-07-27 12:30:23.359520',NULL,'95447f877f7fba08e149a7bd3973e1ed7df7d8ff814e4faec6229a9150d87278','332429fb251ebf1f5f88592f01fa5533cb6a97dd76fb0fce155279aefc509c1a','aaac407dfbd73c411f7fa1c2008e85963a3fd06e9afafa72136b14b5a1e3d8ec'),
(312,'medical_aid',0,'READ',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-27 12:30:23.526470',NULL,'0a6e404f5ed979060e34c508002016dc365439b318689f1cddb3d10f7ca8c36f','f9f5af2f368fb4832bc74ae49de81e669f655e399489ce5ed6089a4dbd85387d','95447f877f7fba08e149a7bd3973e1ed7df7d8ff814e4faec6229a9150d87278'),
(313,'medical_aid',0,'READ',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (0 records)','2026-07-27 12:31:08.480150',NULL,'9abe855be7e26f8d1644d03e1d7a82f81fadd21242395770f4dc8834e874fc0d','f9dba0dcd424e17b46831c4cdd40d3dd1d1e17160217656acd6f9232365f93e0','0a6e404f5ed979060e34c508002016dc365439b318689f1cddb3d10f7ca8c36f'),
(314,'medical_aid',0,'READ',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-27 12:31:08.741025',NULL,'123cbaaaa1a73f2958ce3f9a0e88f6a1e3755fa7d909081564cb72a82a7ebb68','73827b308f22b706b321f5b06f822e347b6691ee2bd1ffc7657c9214a169c864','9abe855be7e26f8d1644d03e1d7a82f81fadd21242395770f4dc8834e874fc0d'),
(315,'medical_aid',0,'READ',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (0 records)','2026-07-27 12:31:20.416479',NULL,'cb2a668ab317215d8509d5dcb045b4ee95e86db19809af57a1a754488058ca98','baf2a68894e0a8a516b76f7280f30da587f4705c01354e6ff7673cf742684a4d','123cbaaaa1a73f2958ce3f9a0e88f6a1e3755fa7d909081564cb72a82a7ebb68'),
(316,'medical_aid',0,'READ',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-27 12:31:20.557698',NULL,'a5c1a6ff19bf48bc97300b83dfa6df7a0debdc792b15133df18774a3911dfa63','4238eb4ce57925af3c078c18afa8b76815cf7e328cc41d1055a09fb1d471af74','cb2a668ab317215d8509d5dcb045b4ee95e86db19809af57a1a754488058ca98'),
(317,'medical_aid',0,'READ',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (0 records)','2026-07-27 12:32:18.519989',NULL,'e370fd0e60c2ece6f3099aef4389797b67cca8208c5c15d85809bcba2c41556b','78b28d14fa57fbc886703df16f3a83eb14b7de7e74e4ca8b3d2638801063a548','a5c1a6ff19bf48bc97300b83dfa6df7a0debdc792b15133df18774a3911dfa63'),
(318,'medical_aid',0,'READ',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-27 12:32:18.610836',NULL,'36631760be271691cd0e42b800ee830839136f8d9f10223aef32d6b98254a2bc','d9200d7d2186a5adbe0c124511ff769acd58464fa789ab8d20090fae0c6bc310','e370fd0e60c2ece6f3099aef4389797b67cca8208c5c15d85809bcba2c41556b'),
(319,'medical_aid',0,'READ',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (0 records)','2026-07-27 12:34:21.998510',NULL,'867fa6f137a57c5ad0c66e4e272056cb133a90a54c37575fec19ed1c488027d8','892a7f52915922fe7b959afc4c4da92590f3850c56c8e19017f7005dde351fa6','36631760be271691cd0e42b800ee830839136f8d9f10223aef32d6b98254a2bc'),
(320,'medical_aid',0,'READ',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-27 12:34:22.179648',NULL,'a29869656c16c699c53365e55bd8c0550ee309b2255bf9cb855ccf8d3c42aaf4','79dc000b15b889b195458ee11a2bf6ef35e12a9453da88cd2786671f6fdb9698','867fa6f137a57c5ad0c66e4e272056cb133a90a54c37575fec19ed1c488027d8'),
(321,'medical_aid',0,'READ',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (0 records)','2026-07-27 12:35:16.416588',NULL,'af2827e15a3d3cf19b4d1c13e5568fa8f5dab2fe7a39089a369f1ced657e7402','ce28e40cde9722e8d2c34092af5ae9b3e01bc1f695a247ff3b34d9fead158e20','a29869656c16c699c53365e55bd8c0550ee309b2255bf9cb855ccf8d3c42aaf4'),
(322,'medical_aid',0,'READ',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-27 12:35:16.754157',NULL,'acdec5b4b89e1faa2a1ccdb9d23693f01e017c3b7f53083d9641175cfef0b022','da977aabc458598d33293406bcf9bdc6a986496a1f32838d66a1c966b97f6ab7','af2827e15a3d3cf19b4d1c13e5568fa8f5dab2fe7a39089a369f1ced657e7402'),
(323,'medical_aid',0,'READ',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed medical aid list (0 records)','2026-07-27 12:36:18.347464',NULL,'6df57df9fc046b83a4c2bf254208ccfd620a85b8040ac9f47c768bb7b27f28b2','2e4c4d5f0848ba6eaea6d92a0f7dbff56b5a58238a253a8bae789dd8594c7b62','acdec5b4b89e1faa2a1ccdb9d23693f01e017c3b7f53083d9641175cfef0b022'),
(324,'medical_aid',0,'READ',NULL,NULL,'Treasurer',42,'FREDERICK MADAYAG','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Treasurer viewed returned medical aid list (0 records)','2026-07-27 12:36:18.397297',NULL,'efbe2b9b0b59adf10267747c90db6805358bda60b7e833c405f8aa2ab426a3bf','0a73d813c0c3aeb0590e64649972aed0057b02e86da43d87f276b11f6f3ddbb9','6df57df9fc046b83a4c2bf254208ccfd620a85b8040ac9f47c768bb7b27f28b2');

/*Table structure for table `login_attempt_log` */

DROP TABLE IF EXISTS `login_attempt_log`;

CREATE TABLE `login_attempt_log` (
  `attempt_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `username_used` varchar(150) NOT NULL,
  `ip_address` char(39) NOT NULL,
  `device_info` varchar(255) DEFAULT NULL,
  `result` varchar(50) NOT NULL,
  `attempted_at` datetime(6) NOT NULL,
  `user_id_FK` int(11) DEFAULT NULL,
  PRIMARY KEY (`attempt_id_PK`),
  KEY `LOGIN_ATTEMPT_LOG_user_id_FK_3d7e6e0a_fk_OFFICER_USER_user_id_PK` (`user_id_FK`),
  CONSTRAINT `LOGIN_ATTEMPT_LOG_user_id_FK_3d7e6e0a_fk_OFFICER_USER_user_id_PK` FOREIGN KEY (`user_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=218 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `login_attempt_log` */

insert  into `login_attempt_log`(`attempt_id_PK`,`username_used`,`ip_address`,`device_info`,`result`,`attempted_at`,`user_id_FK`) values 
(1,'president','112.202.47.68','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','account_not_found','2026-07-25 10:19:58.635446',NULL),
(2,'adminvon','112.202.47.68','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Success','2026-07-25 10:20:09.116270',2),
(3,'president','112.202.47.68','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Success','2026-07-25 10:20:16.508665',23),
(4,'Jas','2405:8d40:4c19:b784:d6c:b1ce:53a1:3847','Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','account_not_found','2026-07-25 10:21:16.989842',NULL),
(5,'Jas','2405:8d40:4c19:b784:d6c:b1ce:53a1:3847','Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','account_not_found','2026-07-25 10:21:47.275296',NULL),
(6,'Jas','2405:8d40:4c19:b784:d6c:b1ce:53a1:3847','Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','account_not_found','2026-07-25 10:21:48.806905',NULL),
(7,'treasurer','2405:8d40:4c19:b784:d6c:b1ce:53a1:3847','Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','incorrect_password','2026-07-25 10:22:49.888076',24),
(8,'treasurer','2405:8d40:4c19:b784:d6c:b1ce:53a1:3847','Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','incorrect_password','2026-07-25 10:22:51.873165',24),
(9,'treasurer','2405:8d40:4c19:b784:d6c:b1ce:53a1:3847','Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','incorrect_password','2026-07-25 10:22:53.217720',24),
(10,'auditor','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','Term expired','2026-07-25 10:22:57.560698',25),
(11,'treasurer','2405:8d40:4c19:b784:d6c:b1ce:53a1:3847','Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Success','2026-07-25 10:23:04.487868',24),
(12,'treasurer','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Success','2026-07-25 10:24:29.023514',24),
(13,'auditor','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','Term expired','2026-07-25 10:25:55.275093',25),
(14,'auditor','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','Term expired','2026-07-25 10:25:58.161969',25),
(15,'auditor','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','Term expired','2026-07-25 10:25:59.609478',25),
(16,'auditor','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','Term expired','2026-07-25 10:25:59.807616',25),
(17,'president','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','Success','2026-07-25 10:26:03.574195',23),
(18,'president','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','Success','2026-07-25 10:27:28.729229',23),
(19,'auditor','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Success','2026-07-25 10:33:37.868208',25),
(20,'auditor','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','Success','2026-07-25 10:34:24.316439',25),
(21,'YEGANn','112.198.120.53','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 EdgA/142.0.0.0','pending_treasurer_review','2026-07-25 10:38:17.677288',NULL),
(22,'treasurer','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','Success','2026-07-25 10:39:39.169230',24),
(23,'auditor','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','Success','2026-07-25 10:40:14.522229',25),
(24,'YEGANn','112.198.120.53','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 EdgA/142.0.0.0','pending_president_approval','2026-07-25 10:41:21.045029',NULL),
(25,'YEGANn','112.198.120.53','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 EdgA/142.0.0.0','pending_president_approval','2026-07-25 10:42:29.728560',NULL),
(26,'president','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','Success','2026-07-25 10:42:34.669731',23),
(27,'auditor','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','MFA_REQUIRED','2026-07-25 10:42:49.622560',25),
(28,'auditor','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','Success','2026-07-25 10:43:11.942503',25),
(29,'YEGANn','112.198.120.53','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 EdgA/142.0.0.0','incorrect_password','2026-07-25 10:44:17.294571',26),
(30,'YEGANn','112.198.120.53','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 EdgA/142.0.0.0','incorrect_password','2026-07-25 10:44:20.895797',26),
(31,'YEGANn','112.198.120.53','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 EdgA/142.0.0.0','incorrect_password','2026-07-25 10:44:27.500205',26),
(32,'YEGANn','112.198.120.53','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 EdgA/142.0.0.0','incorrect_password','2026-07-25 10:44:36.578031',26),
(33,'YEGANn','112.198.120.53','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 EdgA/142.0.0.0','incorrect_password','2026-07-25 10:44:40.163847',26),
(34,'YEGANn','112.198.120.53','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 EdgA/142.0.0.0','incorrect_password','2026-07-25 10:44:49.866283',26),
(35,'YEGANn','112.198.120.53','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 EdgA/142.0.0.0','incorrect_password','2026-07-25 10:44:51.508440',26),
(36,'YEGANn','112.198.120.53','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 EdgA/142.0.0.0','incorrect_password','2026-07-25 10:44:55.139324',26),
(37,'YEGANn','112.198.120.53','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 EdgA/142.0.0.0','incorrect_password','2026-07-25 10:44:55.729132',26),
(38,'YEGANn','112.198.120.53','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 EdgA/142.0.0.0','incorrect_password','2026-07-25 10:44:56.433144',26),
(39,'YEGANn','112.198.120.53','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 EdgA/142.0.0.0','incorrect_password','2026-07-25 10:44:56.568476',26),
(40,'YEGANn','112.198.120.53','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 EdgA/142.0.0.0','incorrect_password','2026-07-25 10:44:56.737886',26),
(41,'YEGANn','112.198.120.53','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 EdgA/142.0.0.0','incorrect_password','2026-07-25 10:44:56.885623',26),
(42,'YEGANn','112.198.120.53','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 EdgA/142.0.0.0','incorrect_password','2026-07-25 10:44:57.060502',26),
(43,'YEGANn','112.198.120.53','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 EdgA/142.0.0.0','incorrect_password','2026-07-25 10:44:57.226174',26),
(44,'YEGANn','112.198.120.53','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 EdgA/142.0.0.0','incorrect_password','2026-07-25 10:44:57.422747',26),
(45,'YEGANn','112.198.120.53','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 EdgA/142.0.0.0','incorrect_password','2026-07-25 10:44:57.576687',26),
(46,'YEGANn','112.198.120.53','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 EdgA/142.0.0.0','incorrect_password','2026-07-25 10:44:57.786707',26),
(47,'YEGANn','112.198.120.53','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 EdgA/142.0.0.0','incorrect_password','2026-07-25 10:44:57.979191',26),
(48,'president','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','MFA_REQUIRED','2026-07-25 10:45:00.394268',23),
(49,'YEGANn','112.198.120.53','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 EdgA/142.0.0.0','incorrect_password','2026-07-25 10:45:23.975822',26),
(50,'YEGANn','112.198.120.53','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 EdgA/142.0.0.0','incorrect_password','2026-07-25 10:45:31.546194',26),
(51,'YEGANn','112.198.120.53','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 EdgA/142.0.0.0','incorrect_password','2026-07-25 10:45:39.323385',26),
(52,'YEGANn','112.198.120.53','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 EdgA/142.0.0.0','incorrect_password','2026-07-25 10:46:22.538206',26),
(53,'jasminerotugal@gmail.com','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','pending_treasurer_review','2026-07-25 10:46:23.764087',NULL),
(54,'YEGANn','112.198.120.53','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 EdgA/142.0.0.0','incorrect_password','2026-07-25 10:46:42.434413',26),
(55,'treasurer','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Success','2026-07-25 10:46:46.904071',24),
(56,'142joe1','112.202.47.68','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','pending_treasurer_review','2026-07-25 10:48:20.170415',NULL),
(57,'142joe1','112.202.47.68','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','pending_auditor_review','2026-07-25 10:48:59.670669',NULL),
(58,'auditor','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','MFA_REQUIRED','2026-07-25 10:49:19.863094',25),
(59,'142joe1','112.202.47.68','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Success','2026-07-25 10:51:33.890638',27),
(60,'YEGANn2','112.198.120.53','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 EdgA/142.0.0.0','pending_treasurer_review','2026-07-25 10:52:00.919304',NULL),
(61,'auditor','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','MFA_REQUIRED','2026-07-25 10:52:17.038657',25),
(62,'treasurer','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Success','2026-07-25 10:52:47.726329',24),
(63,'YEGANn2','112.198.120.53','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 EdgA/142.0.0.0','Success','2026-07-25 10:53:55.313413',29),
(64,'jasminerotugal@gmail.com','131.226.99.58','Mozilla/5.0 (Linux; Android 15; CPH2591 Build/AP3A.240617.008; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/150.0.7871.124 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/570.0.0.34.87;]','incorrect_password','2026-07-25 10:55:27.342466',28),
(65,'jasminerotugal@gmail.com','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','incorrect_password','2026-07-25 10:56:37.091796',28),
(66,'jasminerotugal@gmail.com','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','incorrect_password','2026-07-25 10:56:39.337042',28),
(67,'jasminerotugal@gmail.com','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','incorrect_password','2026-07-25 10:56:51.157945',28),
(68,'jasminerotugal@gmail.com','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','incorrect_password','2026-07-25 10:56:51.679194',28),
(69,'jasminerotugal@gmail.com','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','incorrect_password','2026-07-25 10:56:51.932433',28),
(70,'jasminerotugal@gmail.com','131.226.99.58','Mozilla/5.0 (Linux; Android 15; CPH2591 Build/AP3A.240617.008; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/150.0.7871.124 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/570.0.0.34.87;]','Success','2026-07-25 11:01:20.305209',28),
(71,'YEGANn2','112.198.120.53','Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Success','2026-07-25 11:01:45.139256',29),
(72,'auditor','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','MFA_REQUIRED','2026-07-25 11:06:29.369859',25),
(73,'auditor','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','MFA_REQUIRED','2026-07-25 11:07:00.663829',25),
(74,'auditor','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','MFA_REQUIRED','2026-07-25 11:07:02.625748',25),
(75,'auditor','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','Success','2026-07-25 11:07:51.172301',25),
(76,'treasurer','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Success','2026-07-25 11:09:51.433109',24),
(77,'treasurer','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','Success','2026-07-25 11:09:52.252921',24),
(78,'auditor','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','MFA_REQUIRED','2026-07-25 11:20:47.898800',25),
(79,'auditor','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','MFA_REQUIRED','2026-07-25 11:20:48.081940',25),
(80,'auditor','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','Success','2026-07-25 11:21:28.421927',25),
(81,'treasurer','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','Success','2026-07-25 11:31:35.292852',24),
(82,'auditor','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','MFA_REQUIRED','2026-07-25 11:32:37.556623',25),
(83,'auditor','112.198.120.53','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0','Success','2026-07-25 11:33:12.396568',25),
(84,'treasurer_admin','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','account_not_found','2026-07-25 11:45:35.699502',NULL),
(85,'treasurer_admin','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','account_not_found','2026-07-25 11:45:42.973131',NULL),
(86,'treasurer','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Success','2026-07-25 11:46:10.113222',24),
(87,'auditor_admin','212.102.51.117','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','account_not_found','2026-07-25 11:57:06.168095',NULL),
(88,'142joe','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','account_not_found','2026-07-26 00:07:38.836434',NULL),
(89,'142joe1','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','incorrect_password','2026-07-26 00:07:45.856781',27),
(90,'142joe1','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Success','2026-07-26 00:07:58.454667',27),
(91,'president','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','MFA_REQUIRED','2026-07-26 00:09:53.822108',23),
(92,'president','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Success','2026-07-26 00:11:02.988042',23),
(93,'secretary','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Term expired','2026-07-26 00:12:26.549931',30),
(94,'president','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','MFA_REQUIRED','2026-07-26 00:12:39.985650',23),
(95,'president','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Success','2026-07-26 00:12:53.797806',23),
(96,'secretary','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Term expired','2026-07-26 00:13:15.404186',30),
(97,'president','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','incorrect_password','2026-07-26 00:13:25.594049',23),
(98,'president','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','MFA_REQUIRED','2026-07-26 00:13:28.498984',23),
(99,'president','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Success','2026-07-26 00:13:31.551996',23),
(100,'secretary','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Success','2026-07-26 00:13:53.640250',30),
(101,'142joe1','192.168.1.3','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Success','2026-07-26 04:00:09.480259',27),
(102,'142joe1','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Success','2026-07-26 05:57:01.695935',27),
(103,'142joe1','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Success','2026-07-26 05:57:04.633890',27),
(104,'president','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','MFA_REQUIRED','2026-07-26 08:18:26.150150',23),
(105,'president','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','MFA_REQUIRED','2026-07-26 08:21:41.262202',23),
(106,'president','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Success','2026-07-26 08:21:56.114387',23),
(107,'treasurer','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Success','2026-07-26 08:22:08.275984',24),
(108,'auditor','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','MFA_REQUIRED','2026-07-26 08:22:20.051631',25),
(109,'auditor','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Success','2026-07-26 08:27:44.520719',25),
(110,'142joe','192.168.1.3','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','pending_auditor_review','2026-07-26 08:45:50.657129',NULL),
(111,'142joe','192.168.1.3','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','pending_president_approval','2026-07-26 08:47:06.962134',NULL),
(112,'142joe','192.168.1.3','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Success','2026-07-26 08:48:41.890855',31),
(113,'142joe8','192.168.1.3','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','pending_auditor_review','2026-07-26 10:07:08.101681',NULL),
(114,'142joe7','192.168.1.3','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Success','2026-07-26 10:08:07.581382',37),
(115,'142joe8','192.168.1.3','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Success','2026-07-26 10:13:42.080610',38),
(116,'142joe8','192.168.1.3','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Success','2026-07-26 10:19:40.014659',38),
(117,'142joe8','192.168.1.3','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','incorrect_password','2026-07-26 10:19:50.686596',38),
(118,'142joe8','192.168.1.3','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','incorrect_password','2026-07-26 10:19:58.594433',38),
(119,'142joe8','192.168.1.3','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Success','2026-07-26 10:20:06.333176',38),
(120,'secretary','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Success','2026-07-26 10:20:29.457657',30),
(121,'142joe8','192.168.1.3','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Success','2026-07-26 10:31:16.187582',38),
(122,'142joe1','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Desktop login blocked for member','2026-07-26 10:40:29.119421',27),
(123,'142joe1','127.0.0.1','Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Success','2026-07-26 10:40:35.928305',27),
(124,'142joe1','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','incorrect_password','2026-07-26 10:43:42.483087',27),
(125,'142joe1','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Desktop login blocked for member','2026-07-26 10:43:46.991870',27),
(126,'142joe1','127.0.0.1','Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Desktop login blocked for member','2026-07-26 10:43:52.313991',27),
(127,'142joe1','127.0.0.1','Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Desktop login blocked for member','2026-07-26 10:43:53.777316',27),
(128,'142joe1','127.0.0.1','Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Desktop login blocked for member','2026-07-26 10:43:54.102503',27),
(129,'142joe1','127.0.0.1','Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Desktop login blocked for member','2026-07-26 10:43:54.262543',27),
(130,'142joe1','127.0.0.1','Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Desktop login blocked for member','2026-07-26 10:43:54.387117',27),
(131,'142joe1','127.0.0.1','Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Desktop login blocked for member','2026-07-26 10:43:54.522752',27),
(132,'142joe1','127.0.0.1','Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Desktop login blocked for member','2026-07-26 10:43:54.654519',27),
(133,'142joe1','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Desktop login blocked for member','2026-07-26 10:44:02.322777',27),
(134,'142joe1','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Desktop login blocked for member','2026-07-26 10:44:02.482830',27),
(135,'142joe1','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Desktop login blocked for member','2026-07-26 10:44:02.629871',27),
(136,'142joe1','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Desktop login blocked for member','2026-07-26 10:44:02.797550',27),
(137,'142joe1','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Desktop login blocked for member','2026-07-26 10:44:02.915564',27),
(138,'142joe1','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Desktop login blocked for member','2026-07-26 10:44:03.057023',27),
(139,'142joe1','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Desktop login blocked for member','2026-07-26 10:44:03.219963',27),
(140,'142joe','127.0.0.1','Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','inactive_account','2026-07-26 10:44:18.903170',31),
(141,'142joe1','127.0.0.1','Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Desktop login blocked for member','2026-07-26 10:44:34.957102',27),
(142,'142joe8','192.168.1.3','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','incorrect_password','2026-07-26 10:46:09.298723',38),
(143,'142joe8','192.168.1.3','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Desktop login blocked for member','2026-07-26 10:46:17.323954',38),
(144,'142joe8','127.0.0.1','Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','incorrect_password','2026-07-26 10:47:55.901005',38),
(145,'142joe8','127.0.0.1','Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Success','2026-07-26 10:48:02.121070',38),
(146,'142joe8','192.168.1.3','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Success','2026-07-26 10:48:16.928974',38),
(147,'142joe8','192.168.1.3','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Desktop login blocked for member','2026-07-26 10:52:05.649422',38),
(148,'142joe8','192.168.1.3','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Desktop login blocked for member','2026-07-26 10:52:33.584022',38),
(149,'142joe8','192.168.1.3','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Success','2026-07-26 10:54:42.976014',38),
(150,'142joe8','192.168.1.3','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Success','2026-07-26 10:55:50.136642',38),
(151,'142joe8','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Desktop login blocked for member','2026-07-26 10:56:04.037280',38),
(152,'142joe8','127.0.0.1','Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Success','2026-07-26 10:56:11.473030',38),
(153,'142joe','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','incorrect_password','2026-07-26 11:01:08.285237',31),
(154,'142joe8','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Desktop login blocked for member','2026-07-26 11:01:11.834373',38),
(155,'142joe8','127.0.0.1','Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Success','2026-07-26 11:01:16.801694',38),
(156,'secretary','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Success','2026-07-27 07:45:19.030374',30),
(157,'142joe7','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','incorrect_password','2026-07-27 07:46:46.147288',37),
(158,'142joe7','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','incorrect_password','2026-07-27 07:46:52.823212',37),
(159,'142joe7','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','incorrect_password','2026-07-27 07:46:53.929688',37),
(160,'142joe7','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','incorrect_password','2026-07-27 07:46:57.223650',37),
(161,'142joe7','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Desktop login blocked for member','2026-07-27 07:46:58.716077',37),
(162,'142joe7','127.0.0.1','Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1','Success','2026-07-27 07:47:06.577205',37),
(163,'142joe8','127.0.0.1','Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1','incorrect_password','2026-07-27 08:21:15.449614',38),
(164,'142joe7','127.0.0.1','Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1','Success','2026-07-27 08:21:18.494693',37),
(165,'142joe7','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','incorrect_password','2026-07-27 08:34:42.331566',37),
(166,'142joe7','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Desktop login blocked for member','2026-07-27 08:34:47.268961',37),
(167,'142joe7','127.0.0.1','Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1','Success','2026-07-27 08:34:59.210713',37),
(168,'vonadmin','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','account_not_found','2026-07-27 11:41:33.722974',NULL),
(169,'adminvon','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','account_not_found','2026-07-27 11:41:38.602700',NULL),
(170,'adminvon','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','account_not_found','2026-07-27 11:41:41.076548',NULL),
(171,'vonadmin','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','account_not_found','2026-07-27 11:41:50.724480',NULL),
(172,'vonadmin','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','account_not_found','2026-07-27 11:41:51.083470',NULL),
(173,'vonadmin','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','account_not_found','2026-07-27 11:41:51.495826',NULL),
(174,'vonadmin','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','account_not_found','2026-07-27 11:41:51.817872',NULL),
(175,'vonadmin','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','account_not_found','2026-07-27 11:41:51.994756',NULL),
(176,'vonadmin','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','account_not_found','2026-07-27 11:41:52.135877',NULL),
(177,'vonadmin','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','account_not_found','2026-07-27 11:46:13.734973',NULL),
(178,'vonadmin','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','account_not_found','2026-07-27 11:46:14.151523',NULL),
(179,'vonadmin','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','account_not_found','2026-07-27 11:46:14.760972',NULL),
(180,'adminvon','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Success','2026-07-27 11:46:18.465199',40),
(181,'president','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','incorrect_password','2026-07-27 11:46:31.036266',41),
(182,'president','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Success','2026-07-27 11:46:35.740814',41),
(183,'142joe','192.168.1.4','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','pending_treasurer_review','2026-07-27 11:51:20.502668',NULL),
(184,'treasurer','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Success','2026-07-27 11:51:34.125638',42),
(185,'auditor','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','incorrect_password','2026-07-27 11:52:09.281702',43),
(186,'auditor','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','incorrect_password','2026-07-27 11:52:16.894575',43),
(187,'auditor','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','incorrect_password','2026-07-27 11:52:17.404632',43),
(188,'auditor','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','incorrect_password','2026-07-27 11:52:17.647354',43),
(189,'auditor','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Success','2026-07-27 11:52:30.098633',43),
(190,'142joe','192.168.1.4','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','pending_auditor_review','2026-07-27 11:52:42.773166',NULL),
(191,'142joe','192.168.1.4','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','pending_president_approval','2026-07-27 11:53:33.993333',NULL),
(192,'142joe','192.168.1.4','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Success','2026-07-27 11:54:54.185056',45),
(193,'secretary','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Success','2026-07-27 11:59:37.785141',44),
(194,'142joe1','192.168.1.4','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','account_not_found','2026-07-27 12:04:17.378122',NULL),
(195,'142joe2','192.168.1.4','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','incorrect_password','2026-07-27 12:04:20.128433',46),
(196,'142joe2','192.168.1.4','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Success','2026-07-27 12:04:29.110789',46),
(197,'142joe','192.168.1.4','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Success','2026-07-27 12:36:44.545332',45),
(198,'secretary','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Success','2026-07-28 08:07:20.053496',44),
(199,'142joe7','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','account_not_found','2026-07-28 08:07:37.724183',NULL),
(200,'142joe8','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','account_not_found','2026-07-28 08:07:40.614958',NULL),
(201,'142joe8','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','account_not_found','2026-07-28 08:07:41.609340',NULL),
(202,'142joe8','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','account_not_found','2026-07-28 08:07:42.173662',NULL),
(203,'142joe8','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','account_not_found','2026-07-28 08:07:42.359907',NULL),
(204,'142joe','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Desktop login blocked for member','2026-07-28 08:07:47.473610',45),
(205,'142joe','127.0.0.1','Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Success','2026-07-28 08:07:53.431835',45),
(206,'secretary','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Success','2026-07-28 09:09:23.502195',44),
(207,'142joe','127.0.0.1','Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1','Success','2026-07-28 09:11:26.843600',45),
(208,'142joe','192.168.1.4','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Success','2026-07-28 09:29:22.029644',45),
(209,'142joe','127.0.0.1','Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1','Success','2026-07-28 12:52:24.833846',45),
(210,'secretary','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Success','2026-07-28 22:24:53.996914',44),
(211,'secretary','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Success','2026-07-28 22:24:54.036802',44),
(212,'142joe','192.168.1.4','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Success','2026-07-28 22:26:52.855494',45),
(213,'142joe','127.0.0.1','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36','Desktop login blocked for member','2026-07-29 10:05:02.566672',45),
(214,'142joe','127.0.0.1','Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1','Success','2026-07-29 10:05:08.978067',45),
(215,'142joe1','192.168.1.4','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','account_not_found','2026-07-29 10:43:58.387655',NULL),
(216,'142joe','192.168.1.4','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','incorrect_password','2026-07-29 10:44:01.830889',45),
(217,'142joe','192.168.1.4','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36','Success','2026-07-29 10:44:10.011308',45);

/*Table structure for table `medical_aid` */

DROP TABLE IF EXISTS `medical_aid`;

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
  KEY `MEDICAL_AID_released_by_user_id_FK_77cb71e1` (`released_by_user_id_FK`),
  CONSTRAINT `MEDICAL_AID_auditor_verified_by__d16afda1_fk_OFFICER_U` FOREIGN KEY (`auditor_verified_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`),
  CONSTRAINT `MEDICAL_AID_member_id_FK_a3f6c869_fk_MEMBER_member_id_PK` FOREIGN KEY (`member_id_FK`) REFERENCES `member` (`member_id_PK`),
  CONSTRAINT `MEDICAL_AID_president_decided_by_8781c5c8_fk_OFFICER_U` FOREIGN KEY (`president_decided_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`),
  CONSTRAINT `MEDICAL_AID_treasurer_validated__621f73b2_fk_OFFICER_U` FOREIGN KEY (`treasurer_validated_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `medical_aid` */

insert  into `medical_aid`(`medical_aid_id_PK`,`request_date`,`hospital_bill_amount`,`claim_year`,`document_status`,`policy_record_status`,`validated_aid_amount`,`status`,`president_decision`,`release_reference`,`acknowledgement_reference`,`member_id_FK`,`auditor_verified_by_user_id_FK`,`president_decided_by_user_id_FK`,`released_by_user_id_FK`,`treasurer_validated_by_user_id_FK`,`requested_amount`,`hospital_name`,`hospital_date`,`disbursement_source`,`admission_date`,`discharge_date`,`hospital_address`,`reason_for_request`) values 
(1,'2026-07-25',200000.00,2026,'Pending','Pending',0.00,'Auditor Verified',NULL,NULL,NULL,3,NULL,NULL,NULL,24,200000.00,'Fjh',NULL,NULL,'2026-07-05','2026-07-30','Dfh','Ddgg');

/*Table structure for table `member` */

DROP TABLE IF EXISTS `member`;

CREATE TABLE `member` (
  `member_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `full_name` varchar(255) NOT NULL,
  `contact_number` varchar(50) DEFAULT NULL,
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
  `emergency_number` varchar(50) DEFAULT NULL,
  `setup_complete` tinyint(1) NOT NULL,
  `qr_data` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`member_id_PK`),
  UNIQUE KEY `MEMBER_employee_id_6c5f9503_uniq` (`employee_id`),
  KEY `MEMBER_department_id_FK_4098768a_fk_DEPARTMENT_department_id_PK` (`department_id_FK`),
  KEY `MEMBER_officer_user_id_FK_884d61d4_fk_OFFICER_USER_user_id_PK` (`officer_user_id_FK`),
  CONSTRAINT `MEMBER_department_id_FK_4098768a_fk_DEPARTMENT_department_id_PK` FOREIGN KEY (`department_id_FK`) REFERENCES `department` (`department_id_PK`),
  CONSTRAINT `MEMBER_officer_user_id_FK_884d61d4_fk_OFFICER_USER_user_id_PK` FOREIGN KEY (`officer_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=15 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `member` */

insert  into `member`(`member_id_PK`,`full_name`,`contact_number`,`email`,`employment_status`,`membership_status`,`member_type`,`date_joined`,`department`,`employee_id`,`position`,`department_id_FK`,`officer_user_id_FK`,`profile_picture`,`pin_code`,`qr_code`,`emergency_contact`,`emergency_number`,`setup_complete`,`qr_data`) values 
(13,'JUSTIN VON T VERGARA','09050236708','justinvon.vergara_cyn@isu.edu.ph','Active','Permanent','Member','2026-07-27','CCSICT','142joe','ASSISTANT PROFESSOR 3',NULL,45,'profile_pics/3215_IPJZ11j.jpg','15851977099599132616dc8b95fbcd41f21a1039181002d19cf7a4ecc484759f','qr_codes/3162_mlc1RMz.png','EFIPANIO S VERGARA JR','12334567897',1,'ISU-BUJKID4'),
(14,'TRISTAN R ILLARDE','44444444444','kangsoohwa233@gmail.com','Active','Permanent','Member','2026-07-27','SAS','142joe2','INSTRUCTOR 1',NULL,46,'profile_pics/3220_Lyvo9kZ.jpg','8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92','qr_codes/3186_3JRviqG.jpg','PAUL VERSOZA','12345678794',1,'23-15472');

/*Table structure for table `member_ledger` */

DROP TABLE IF EXISTS `member_ledger`;

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
  KEY `MEMBER_LEDG_member__9bc074_idx` (`member_id_FK`),
  KEY `MEMBER_LEDG_transac_4c41b6_idx` (`transaction_type`),
  KEY `MEMBER_LEDG_recorde_fa4ecd_idx` (`recorded_at`),
  CONSTRAINT `MEMBER_LEDGER_member_id_FK_a12f12a2_fk_MEMBER_member_id_PK` FOREIGN KEY (`member_id_FK`) REFERENCES `member` (`member_id_PK`),
  CONSTRAINT `MEMBER_LEDGER_recorded_by_user_id__ea4dfc59_fk_OFFICER_U` FOREIGN KEY (`recorded_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `member_ledger` */

/*Table structure for table `member_registration_request` */

DROP TABLE IF EXISTS `member_registration_request`;

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
  PRIMARY KEY (`request_id_PK`),
  KEY `MEMBER_REGISTRATION__auditor_verified_by__fd89364e_fk_OFFICER_U` (`auditor_verified_by_user_id_FK`),
  KEY `MEMBER_REGISTRATION__president_approved_b_8619f09f_fk_OFFICER_U` (`president_approved_by_user_id_FK`),
  KEY `MEMBER_REGISTRATION__treasurer_verified_b_a88205c4_fk_OFFICER_U` (`treasurer_verified_by_user_id_FK`),
  CONSTRAINT `MEMBER_REGISTRATION__auditor_verified_by__fd89364e_fk_OFFICER_U` FOREIGN KEY (`auditor_verified_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`),
  CONSTRAINT `MEMBER_REGISTRATION__president_approved_b_8619f09f_fk_OFFICER_U` FOREIGN KEY (`president_approved_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`),
  CONSTRAINT `MEMBER_REGISTRATION__treasurer_verified_b_a88205c4_fk_OFFICER_U` FOREIGN KEY (`treasurer_verified_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=15 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `member_registration_request` */

insert  into `member_registration_request`(`request_id_PK`,`full_name`,`employee_id`,`email`,`department`,`position`,`membership_category`,`payment_method`,`amount`,`receipt_number`,`reference_number`,`payment_date`,`status`,`returned_reason`,`submitted_at`,`updated_at`,`submitted_by_ip`,`submitted_by_user_agent`,`processed_by_user_id_FK`,`password_hash`,`auditor_verified_by_user_id_FK`,`president_approved_by_user_id_FK`,`treasurer_verified_by_user_id_FK`) values 
(13,'JUSTIN VON T VERGARA','142joe','justinvon.vergara_cyn@isu.edu.ph','CCSICT','ASSISTANT PROFESSOR 3','Permanent','Bank Transfer',100.00,'REG-20260727115050-142joe',NULL,'2026-07-27','President Approved',NULL,'2026-07-27 11:50:50.010361','2026-07-27 11:54:00.918171','192.168.1.4','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36',42,'64eb810e2de910cbb751c867e7ece346e6ff5c81c22dc6cddc313388ddc9097a',43,41,42),
(14,'TRISTAN R ILLARDE','142joe2','kangsoohwa233@gmail.com','SAS','INSTRUCTOR 1','Permanent','GCash',100.00,'REG-20260727120209-142joe2',NULL,'2026-07-27','President Approved',NULL,'2026-07-27 12:02:09.753484','2026-07-27 12:03:49.279135','192.168.1.4','Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36',42,'64eb810e2de910cbb751c867e7ece346e6ff5c81c22dc6cddc313388ddc9097a',43,41,42);

/*Table structure for table `membership_fee` */

DROP TABLE IF EXISTS `membership_fee`;

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
  KEY `MEMBERSHIP_FEE_recorded_by_user_id__e50e2c50_fk_OFFICER_U` (`recorded_by_user_id_FK`),
  CONSTRAINT `MEMBERSHIP_FEE_member_id_FK_ea282b64_fk_MEMBER_member_id_PK` FOREIGN KEY (`member_id_FK`) REFERENCES `member` (`member_id_PK`),
  CONSTRAINT `MEMBERSHIP_FEE_recorded_by_user_id__e50e2c50_fk_OFFICER_U` FOREIGN KEY (`recorded_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=15 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `membership_fee` */

insert  into `membership_fee`(`fee_id_PK`,`amount`,`payment_date`,`payment_status`,`receipt_number`,`deposit_reference`,`member_id_FK`,`recorded_by_user_id_FK`,`payment_method`) values 
(13,100.00,'2026-07-27','Full Payment','REG-20260727115050-142joe',NULL,13,41,'Bank Transfer'),
(14,100.00,'2026-07-27','Full Payment','REG-20260727120209-142joe2',NULL,14,41,'GCash');

/*Table structure for table `minutes` */

DROP TABLE IF EXISTS `minutes`;

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
  KEY `MINUTES_document_id_FK_3dab1eff_fk_DOCUMENT_document_id_PK` (`document_id_FK`),
  CONSTRAINT `MINUTES_document_id_FK_3dab1eff_fk_DOCUMENT_document_id_PK` FOREIGN KEY (`document_id_FK`) REFERENCES `document` (`document_id_PK`),
  CONSTRAINT `MINUTES_event_id_FK_352800da_fk_EVENT_event_id_PK` FOREIGN KEY (`event_id_FK`) REFERENCES `event` (`event_id_PK`),
  CONSTRAINT `MINUTES_prepared_by_user_id__f10e2bf9_fk_OFFICER_U` FOREIGN KEY (`prepared_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `minutes` */

/*Table structure for table `monthly_dues` */

DROP TABLE IF EXISTS `monthly_dues`;

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
  PRIMARY KEY (`dues_id_PK`),
  KEY `MONTHLY_DUES_member_id_FK_70adcf99_fk_MEMBER_member_id_PK` (`member_id_FK`),
  KEY `MONTHLY_DUES_recorded_by_user_id__a84ebfb3_fk_OFFICER_U` (`recorded_by_user_id_FK`),
  KEY `MONTHLY_DUES_treasurer_id_FK_2ce5f468_fk_OFFICER_USER_user_id_PK` (`treasurer_id_FK`),
  KEY `MONTHLY_DUES_auditor_id_FK_fd49c27d_fk_OFFICER_USER_user_id_PK` (`auditor_id_FK`),
  KEY `MONTHLY_DUES_president_id_FK_08476f2c_fk_OFFICER_USER_user_id_PK` (`president_id_FK`),
  CONSTRAINT `MONTHLY_DUES_auditor_id_FK_fd49c27d_fk_OFFICER_USER_user_id_PK` FOREIGN KEY (`auditor_id_FK`) REFERENCES `officer_user` (`user_id_PK`),
  CONSTRAINT `MONTHLY_DUES_member_id_FK_70adcf99_fk_MEMBER_member_id_PK` FOREIGN KEY (`member_id_FK`) REFERENCES `member` (`member_id_PK`),
  CONSTRAINT `MONTHLY_DUES_president_id_FK_08476f2c_fk_OFFICER_USER_user_id_PK` FOREIGN KEY (`president_id_FK`) REFERENCES `officer_user` (`user_id_PK`),
  CONSTRAINT `MONTHLY_DUES_recorded_by_user_id__a84ebfb3_fk_OFFICER_U` FOREIGN KEY (`recorded_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`),
  CONSTRAINT `MONTHLY_DUES_treasurer_id_FK_2ce5f468_fk_OFFICER_USER_user_id_PK` FOREIGN KEY (`treasurer_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `monthly_dues` */

/*Table structure for table `notification` */

DROP TABLE IF EXISTS `notification`;

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
  PRIMARY KEY (`notification_id_PK`),
  KEY `NOTIFICATION_related_post_id_FK_e61541a2_fk_AID_TRACK` (`related_post_id_FK`),
  CONSTRAINT `NOTIFICATION_related_post_id_FK_e61541a2_fk_AID_TRACK` FOREIGN KEY (`related_post_id_FK`) REFERENCES `aid_tracking_post` (`post_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `notification` */

/*Table structure for table `officer_user` */

DROP TABLE IF EXISTS `officer_user`;

CREATE TABLE `officer_user` (
  `user_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `full_name` varchar(255) NOT NULL,
  `username` varchar(150) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `role` varchar(50) NOT NULL,
  `account_status` varchar(50) NOT NULL,
  `term_start` date DEFAULT NULL,
  `term_end` date DEFAULT NULL,
  `mfa_secret` varchar(255) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `mfa_enabled` tinyint(1) NOT NULL,
  `last_mfa_email_sent_at` datetime(6) DEFAULT NULL,
  `department_id_FK` int(11) DEFAULT NULL,
  `email` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`user_id_PK`),
  UNIQUE KEY `username` (`username`),
  KEY `OFFICER_USER_department_id_FK_cc12815d_fk_DEPARTMEN` (`department_id_FK`),
  CONSTRAINT `OFFICER_USER_department_id_FK_cc12815d_fk_DEPARTMEN` FOREIGN KEY (`department_id_FK`) REFERENCES `department` (`department_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=47 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `officer_user` */

insert  into `officer_user`(`user_id_PK`,`full_name`,`username`,`password_hash`,`role`,`account_status`,`term_start`,`term_end`,`mfa_secret`,`created_at`,`updated_at`,`mfa_enabled`,`last_mfa_email_sent_at`,`department_id_FK`,`email`) values 
(39,'System Backfill','system_backfill','','System','Inactive',NULL,NULL,NULL,'2026-07-22 11:56:41.818208','2026-07-22 11:56:41.818208',0,NULL,NULL,NULL),
(40,'Superadmin Admin Von','adminvon','3b506d4da7b78c2d1504c0d487e6f1c6bec5ad0a6db040d51a7b5d2444121a0b','Superadmin','Active',NULL,NULL,NULL,'2026-07-22 12:07:09.665684','2026-07-22 12:07:09.665684',0,NULL,NULL,'adminvon@caufa.local'),
(41,'President Account','president','3b506d4da7b78c2d1504c0d487e6f1c6bec5ad0a6db040d51a7b5d2444121a0b','President','Active',NULL,NULL,'e334a2dd92e3b30720413a2ce4942e3a','2026-07-27 11:46:18.605147','2026-07-27 11:47:35.072336',1,NULL,NULL,'programmingproject06@gmail.com'),
(42,'FREDERICK MADAYAG','treasurer','cfec7d62a2bfdf1f7aa9835a934afe43fa3eeb30125222abf01cfce4680a17bf','Treasurer','Active','2026-07-27','2026-12-01',NULL,'2026-07-27 11:47:21.836186','2026-07-27 11:47:21.836186',0,NULL,NULL,'vdark699@gmail.com'),
(43,'RHOMAR MANARANG','auditor','5b92db4dfb561dc69c949f34d36f5db0f8b30811be3a2949d85c5001279e9b1a','Auditor','Active','2026-07-27','2026-12-01','b58541949c152c2ff62daf455cc78d5b','2026-07-27 11:48:14.191898','2026-07-27 11:52:27.226301',1,NULL,NULL,'vergarajustin636@gmail.com'),
(44,'JASMINE ROTUGAL','secretary','dece17bb4784e2c98ce3119aee61310465fcc7542780852d2b1ef3b50f3374b9','Secretary','Active','2026-07-27','2026-12-01',NULL,'2026-07-27 11:49:15.037630','2026-07-27 11:49:15.037630',0,NULL,NULL,'jasmine.rotugal_cyn@isu.edu.ph'),
(45,'JUSTIN VON T VERGARA','142joe','64eb810e2de910cbb751c867e7ece346e6ff5c81c22dc6cddc313388ddc9097a','Member','Active',NULL,NULL,NULL,'2026-07-27 11:54:00.889724','2026-07-27 11:54:00.889724',0,NULL,NULL,'justinvon.vergara_cyn@isu.edu.ph'),
(46,'TRISTAN R ILLARDE','142joe2','64eb810e2de910cbb751c867e7ece346e6ff5c81c22dc6cddc313388ddc9097a','Member','Active',NULL,NULL,NULL,'2026-07-27 12:03:49.254978','2026-07-27 12:03:49.254978',0,NULL,NULL,'kangsoohwa233@gmail.com');

/*Table structure for table `organization_fund_report` */

DROP TABLE IF EXISTS `organization_fund_report`;

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
  PRIMARY KEY (`report_id_PK`),
  KEY `ORGANIZATION_FUND_RE_approved_by_user_id__a8823df8_fk_OFFICER_U` (`approved_by_user_id_FK`),
  KEY `ORGANIZATION_FUND_RE_prepared_by_user_id__f419a1e5_fk_OFFICER_U` (`prepared_by_user_id_FK`),
  CONSTRAINT `ORGANIZATION_FUND_RE_approved_by_user_id__a8823df8_fk_OFFICER_U` FOREIGN KEY (`approved_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`),
  CONSTRAINT `ORGANIZATION_FUND_RE_prepared_by_user_id__f419a1e5_fk_OFFICER_U` FOREIGN KEY (`prepared_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `organization_fund_report` */

/*Table structure for table `outgoing_email` */

DROP TABLE IF EXISTS `outgoing_email`;

CREATE TABLE `outgoing_email` (
  `outgoing_email_id` int(11) NOT NULL AUTO_INCREMENT,
  `recipient_list` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`recipient_list`)),
  `subject` varchar(255) NOT NULL,
  `html_template` varchar(255) NOT NULL,
  `context` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`context`)),
  `status` varchar(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `sent_at` datetime(6) DEFAULT NULL,
  `error_message` longtext NOT NULL,
  `retry_count` int(11) NOT NULL,
  PRIMARY KEY (`outgoing_email_id`)
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `outgoing_email` */

insert  into `outgoing_email`(`outgoing_email_id`,`recipient_list`,`subject`,`html_template`,`context`,`status`,`created_at`,`sent_at`,`error_message`,`retry_count`) values 
(1,'[\"manchoco69@gmail.com\"]','CAUFA MFA Verification Code','emails/mfa_challenge.html','{\"full_name\": \"FREDERICK MADAYAG\", \"otp_code\": \"632960\", \"expiry_minutes\": 5}','sent','2026-07-25 10:42:49.610201','2026-07-25 10:42:55.785999','',0),
(2,'[\"vergarajustin636@gmail.com\"]','CAUFA MFA Verification Code','emails/mfa_challenge.html','{\"full_name\": \"President Account\", \"otp_code\": \"716677\", \"expiry_minutes\": 5}','sent','2026-07-25 10:45:00.364686','2026-07-25 10:45:08.371781','',0),
(3,'[\"manchoco69@gmail.com\"]','CAUFA MFA Verification Code','emails/mfa_challenge.html','{\"full_name\": \"FREDERICK MADAYAG\", \"otp_code\": \"478100\", \"expiry_minutes\": 5}','sent','2026-07-25 10:49:19.831405','2026-07-25 10:49:25.666057','',0),
(4,'[\"manchoco69@gmail.com\"]','CAUFA MFA Verification Code','emails/mfa_challenge.html','{\"full_name\": \"FREDERICK MADAYAG\", \"otp_code\": \"599503\", \"expiry_minutes\": 5}','sent','2026-07-25 11:06:29.354843','2026-07-25 11:06:37.124534','',0),
(5,'[\"manchoco69@gmail.com\"]','CAUFA MFA Verification Code','emails/mfa_challenge.html','{\"full_name\": \"FREDERICK MADAYAG\", \"otp_code\": \"462218\", \"expiry_minutes\": 5}','sent','2026-07-25 11:20:47.876448','2026-07-25 11:20:55.452673','',0),
(6,'[\"manchoco69@gmail.com\"]','CAUFA MFA Verification Code','emails/mfa_challenge.html','{\"full_name\": \"FREDERICK MADAYAG\", \"otp_code\": \"056212\", \"expiry_minutes\": 5}','sent','2026-07-25 11:32:37.516595','2026-07-25 11:32:44.274476','',0),
(7,'[\"vergarajustin636@gmail.com\"]','CAUFA MFA Verification Code','emails/mfa_challenge.html','{\"full_name\": \"President Account\", \"otp_code\": \"595405\", \"expiry_minutes\": 5}','sent','2026-07-26 00:09:53.795883','2026-07-26 00:10:01.178202','',0),
(8,'[\"vergarajustin636@gmail.com\"]','CAUFA MFA Verification Code','emails/mfa_challenge.html','{\"full_name\": \"President Account\", \"otp_code\": \"063113\", \"expiry_minutes\": 5}','sent','2026-07-26 08:18:26.077916','2026-07-26 08:18:32.836798','',0),
(9,'[\"manchoco69@gmail.com\"]','CAUFA MFA Verification Code','emails/mfa_challenge.html','{\"full_name\": \"FREDERICK MADAYAG\", \"otp_code\": \"524540\", \"expiry_minutes\": 5}','sent','2026-07-26 08:22:20.032139','2026-07-26 08:22:25.627136','',0);

/*Table structure for table `payroll_batch` */

DROP TABLE IF EXISTS `payroll_batch`;

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
  KEY `PAYROLL_BATCH_returned_by_user_id__25fe28ed_fk_OFFICER_U` (`returned_by_user_id_FK`),
  CONSTRAINT `PAYROLL_BATCH_archive_id_FK_c8cd48a0_fk_transacti` FOREIGN KEY (`archive_id_FK`) REFERENCES `transaction_archive` (`archive_id_PK`),
  CONSTRAINT `PAYROLL_BATCH_auditor_verified_by__1214d668_fk_OFFICER_U` FOREIGN KEY (`auditor_verified_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`),
  CONSTRAINT `PAYROLL_BATCH_president_approved_b_d7cb885f_fk_OFFICER_U` FOREIGN KEY (`president_approved_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`),
  CONSTRAINT `PAYROLL_BATCH_recorded_by_user_id__f63b35cb_fk_OFFICER_U` FOREIGN KEY (`recorded_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`),
  CONSTRAINT `PAYROLL_BATCH_returned_by_user_id__25fe28ed_fk_OFFICER_U` FOREIGN KEY (`returned_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `payroll_batch` */

/*Table structure for table `payroll_deduction` */

DROP TABLE IF EXISTS `payroll_deduction`;

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
  KEY `PAYROLL_DED_batch_i_0b9b21_idx` (`batch_id_FK`,`category`),
  KEY `PAYROLL_DED_member__4008e1_idx` (`member_id_FK`),
  CONSTRAINT `PAYROLL_DEDUCTION_aid_tracking_post_id_14171c63_fk_AID_TRACK` FOREIGN KEY (`aid_tracking_post_id_FK`) REFERENCES `aid_tracking_post` (`post_id_PK`),
  CONSTRAINT `PAYROLL_DEDUCTION_batch_id_FK_ba2e5ff3_fk_PAYROLL_B` FOREIGN KEY (`batch_id_FK`) REFERENCES `payroll_batch` (`batch_id_PK`),
  CONSTRAINT `PAYROLL_DEDUCTION_member_id_FK_4756ee52_fk_MEMBER_member_id_PK` FOREIGN KEY (`member_id_FK`) REFERENCES `member` (`member_id_PK`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `payroll_deduction` */

/*Table structure for table `push_subscription` */

DROP TABLE IF EXISTS `push_subscription`;

CREATE TABLE `push_subscription` (
  `subscription_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `officer_id_FK` int(11) NOT NULL,
  `endpoint` varchar(500) NOT NULL,
  `p256dh_key` varchar(256) NOT NULL,
  `auth_key` varchar(128) NOT NULL,
  `user_agent` varchar(500) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  PRIMARY KEY (`subscription_id_PK`),
  UNIQUE KEY `PUSH_SUBSCRIPTION_officer_id_FK_endpoint_d8da377b_uniq` (`officer_id_FK`,`endpoint`),
  CONSTRAINT `PUSH_SUBSCRIPTION_officer_id_FK_4678cd3d_fk_OFFICER_U` FOREIGN KEY (`officer_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `push_subscription` */

/*Table structure for table `revision_log` */

DROP TABLE IF EXISTS `revision_log`;

CREATE TABLE `revision_log` (
  `log_id` int(11) NOT NULL AUTO_INCREMENT,
  `object_id` int(10) unsigned NOT NULL CHECK (`object_id` >= 0),
  `rejection_reason` longtext NOT NULL,
  `snapshot_data` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`snapshot_data`)),
  `created_at` datetime(6) NOT NULL,
  `auditor_id_FK` int(11) DEFAULT NULL,
  `content_type_id` int(11) NOT NULL,
  PRIMARY KEY (`log_id`),
  KEY `revision_log_auditor_id_FK_86a7849b_fk_OFFICER_USER_user_id_PK` (`auditor_id_FK`),
  KEY `revision_lo_content_6da5e6_idx` (`content_type_id`,`object_id`),
  KEY `revision_lo_created_91651d_idx` (`created_at`),
  CONSTRAINT `revision_log_auditor_id_FK_86a7849b_fk_OFFICER_USER_user_id_PK` FOREIGN KEY (`auditor_id_FK`) REFERENCES `officer_user` (`user_id_PK`),
  CONSTRAINT `revision_log_content_type_id_2e36b96a_fk_django_content_type_id` FOREIGN KEY (`content_type_id`) REFERENCES `django_content_type` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `revision_log` */

/*Table structure for table `sensitive_read_log` */

DROP TABLE IF EXISTS `sensitive_read_log`;

CREATE TABLE `sensitive_read_log` (
  `read_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `module` varchar(100) NOT NULL,
  `record_id` int(11) NOT NULL,
  `purpose` varchar(255) NOT NULL,
  `timestamp` datetime(6) NOT NULL,
  `user_id_FK` int(11) NOT NULL,
  `device_info` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`read_id_PK`),
  KEY `SENSITIVE_READ_LOG_user_id_FK_f41bb5ec_fk_OFFICER_U` (`user_id_FK`),
  CONSTRAINT `SENSITIVE_READ_LOG_user_id_FK_f41bb5ec_fk_OFFICER_U` FOREIGN KEY (`user_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=159 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `sensitive_read_log` */

insert  into `sensitive_read_log`(`read_id_PK`,`module`,`record_id`,`purpose`,`timestamp`,`user_id_FK`,`device_info`) values 
(1,'medical_aid',1,'Treasurer','2026-07-25 11:19:43.620543',24,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(2,'medical_aid',1,'Treasurer','2026-07-25 11:20:21.085670',24,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0'),
(3,'medical_aid',1,'Auditor','2026-07-25 11:21:31.288446',25,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0'),
(4,'medical_aid',1,'Treasurer','2026-07-25 11:22:46.773064',24,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(5,'medical_aid',1,'Treasurer','2026-07-25 11:31:41.779261',24,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0'),
(6,'medical_aid',1,'Treasurer','2026-07-25 11:46:14.491076',24,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(7,'medical_aid',1,'Treasurer','2026-07-25 11:55:15.375831',24,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(8,'medical_aid',1,'President','2026-07-26 00:11:04.294205',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(9,'medical_aid',1,'President','2026-07-26 00:11:04.648044',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(10,'medical_aid',1,'President','2026-07-26 00:12:54.394186',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(11,'medical_aid',1,'President','2026-07-26 00:12:54.747193',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(12,'medical_aid',1,'President','2026-07-26 00:13:32.122077',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(13,'medical_aid',1,'President','2026-07-26 00:13:32.487839',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(14,'medical_aid',1,'President','2026-07-26 08:21:58.619187',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(15,'medical_aid',1,'President','2026-07-26 08:21:59.215901',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(16,'medical_aid',1,'Treasurer','2026-07-26 08:22:10.983647',24,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(17,'medical_aid',1,'President','2026-07-26 08:30:57.583000',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(18,'medical_aid',1,'President','2026-07-26 08:30:58.977419',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(19,'medical_aid',1,'Treasurer','2026-07-26 08:31:10.676886',24,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(20,'medical_aid',1,'President','2026-07-26 08:31:21.401596',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(21,'medical_aid',1,'Treasurer','2026-07-26 08:31:24.620366',24,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(22,'medical_aid',1,'Treasurer','2026-07-26 08:31:35.952855',24,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(23,'medical_aid',1,'Treasurer','2026-07-26 08:31:45.586826',24,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(24,'medical_aid',1,'Treasurer','2026-07-26 08:32:05.160345',24,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(25,'medical_aid',1,'Treasurer','2026-07-26 08:32:27.319221',24,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(26,'medical_aid',1,'Treasurer','2026-07-26 08:32:42.678895',24,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(27,'medical_aid',1,'Treasurer','2026-07-26 08:35:17.001431',24,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(28,'medical_aid',1,'Treasurer','2026-07-26 08:35:50.245690',24,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(29,'medical_aid',1,'Treasurer','2026-07-26 08:35:59.310384',24,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(30,'medical_aid',1,'Treasurer','2026-07-26 08:36:30.199961',24,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(31,'medical_aid',1,'Treasurer','2026-07-26 08:37:02.794197',24,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(32,'medical_aid',1,'Treasurer','2026-07-26 08:37:30.373978',24,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(33,'medical_aid',1,'Treasurer','2026-07-26 08:44:06.303933',24,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(34,'medical_aid',1,'President','2026-07-26 08:46:49.106436',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(35,'medical_aid',1,'President','2026-07-26 08:46:49.800933',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(36,'medical_aid',1,'President','2026-07-26 08:49:12.033974',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(37,'medical_aid',1,'President','2026-07-26 08:49:13.296134',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(38,'medical_aid',1,'Treasurer','2026-07-26 08:49:14.385035',24,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(39,'medical_aid',1,'President','2026-07-26 08:55:27.100708',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(40,'medical_aid',1,'President','2026-07-26 08:55:28.761880',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(41,'medical_aid',1,'Treasurer','2026-07-26 08:55:29.836388',24,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(42,'medical_aid',1,'President','2026-07-26 08:57:49.662267',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(43,'medical_aid',1,'President','2026-07-26 08:57:51.329338',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(44,'medical_aid',1,'Treasurer','2026-07-26 08:57:53.604695',24,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(45,'medical_aid',1,'President','2026-07-26 08:59:16.093618',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(46,'medical_aid',1,'President','2026-07-26 08:59:17.288054',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(47,'medical_aid',1,'Treasurer','2026-07-26 08:59:18.193570',24,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(48,'medical_aid',1,'President','2026-07-26 09:01:21.739372',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(49,'medical_aid',1,'President','2026-07-26 09:01:22.425763',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(50,'medical_aid',1,'Treasurer','2026-07-26 09:06:17.974195',24,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(51,'medical_aid',1,'President','2026-07-26 09:06:18.180182',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(52,'medical_aid',1,'President','2026-07-26 09:12:21.812058',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(53,'medical_aid',1,'President','2026-07-26 09:12:22.929866',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(54,'medical_aid',1,'Treasurer','2026-07-26 09:12:23.899817',24,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(55,'medical_aid',1,'President','2026-07-26 09:21:22.210190',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(56,'medical_aid',1,'President','2026-07-26 09:21:23.305655',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(57,'medical_aid',1,'Treasurer','2026-07-26 09:21:24.061082',24,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(58,'medical_aid',1,'President','2026-07-26 09:26:54.818319',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(59,'medical_aid',1,'President','2026-07-26 09:26:55.851243',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(60,'medical_aid',1,'President','2026-07-26 09:27:09.334347',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(61,'medical_aid',1,'President','2026-07-26 09:27:11.896650',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(62,'medical_aid',1,'Treasurer','2026-07-26 09:27:14.102769',24,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(63,'medical_aid',1,'President','2026-07-26 09:27:32.786114',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(64,'medical_aid',1,'President','2026-07-26 09:27:34.232838',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(65,'medical_aid',1,'Treasurer','2026-07-26 09:27:34.918687',24,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(66,'medical_aid',1,'President','2026-07-26 09:33:02.893468',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(67,'medical_aid',1,'President','2026-07-26 09:33:04.634454',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(68,'medical_aid',1,'Treasurer','2026-07-26 09:33:05.762083',24,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(69,'medical_aid',1,'President','2026-07-26 09:43:22.629954',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(70,'medical_aid',1,'President','2026-07-26 09:43:22.781513',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(71,'medical_aid',1,'President','2026-07-26 09:45:45.670414',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(72,'medical_aid',1,'President','2026-07-26 09:45:46.226777',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(73,'medical_aid',1,'President','2026-07-26 09:46:12.538852',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(74,'medical_aid',1,'President','2026-07-26 09:46:13.317640',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(75,'medical_aid',1,'President','2026-07-26 10:02:01.864592',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(76,'medical_aid',1,'President','2026-07-26 10:02:02.374423',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(77,'medical_aid',1,'President','2026-07-26 10:06:16.924515',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(78,'medical_aid',1,'President','2026-07-26 10:06:17.434515',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(79,'medical_aid',1,'President','2026-07-26 10:06:34.059639',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(80,'medical_aid',1,'President','2026-07-26 10:06:34.947257',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(81,'medical_aid',1,'President','2026-07-26 10:07:11.473791',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(82,'medical_aid',1,'President','2026-07-26 10:07:12.281247',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(83,'medical_aid',1,'President','2026-07-26 10:09:38.178556',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(84,'medical_aid',1,'President','2026-07-26 10:09:39.048733',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(85,'medical_aid',1,'President','2026-07-26 10:11:58.874128',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(86,'medical_aid',1,'President','2026-07-26 10:11:59.307329',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(87,'medical_aid',1,'President','2026-07-26 10:17:53.292084',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(88,'medical_aid',1,'President','2026-07-26 10:17:54.011671',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(89,'medical_aid',1,'President','2026-07-26 10:21:45.413901',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(90,'medical_aid',1,'President','2026-07-26 10:21:46.562767',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(91,'medical_aid',1,'President','2026-07-26 10:22:15.648704',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(92,'medical_aid',1,'President','2026-07-26 10:22:16.125068',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(93,'medical_aid',1,'President','2026-07-26 10:23:15.679997',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(94,'medical_aid',1,'President','2026-07-26 10:23:17.159475',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(95,'medical_aid',1,'President','2026-07-26 10:26:18.996526',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(96,'medical_aid',1,'President','2026-07-26 10:26:21.220290',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(97,'medical_aid',1,'President','2026-07-26 10:26:44.098865',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(98,'medical_aid',1,'President','2026-07-26 10:26:47.881976',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(99,'medical_aid',1,'President','2026-07-26 10:27:07.162273',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(100,'medical_aid',1,'President','2026-07-26 10:27:07.406149',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(101,'medical_aid',1,'President','2026-07-26 10:27:22.712404',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(102,'medical_aid',1,'President','2026-07-26 10:27:23.271349',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(103,'medical_aid',1,'President','2026-07-26 10:27:48.183740',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(104,'medical_aid',1,'President','2026-07-26 10:27:48.654502',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(105,'medical_aid',1,'President','2026-07-26 10:28:31.801656',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(106,'medical_aid',1,'President','2026-07-26 10:28:32.536460',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(107,'medical_aid',1,'President','2026-07-26 10:32:34.861221',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(108,'medical_aid',1,'President','2026-07-26 10:32:35.340585',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(109,'medical_aid',1,'President','2026-07-26 10:33:56.899778',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(110,'medical_aid',1,'President','2026-07-26 10:33:57.595809',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(111,'medical_aid',1,'President','2026-07-26 10:34:12.908607',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(112,'medical_aid',1,'President','2026-07-26 10:34:14.139238',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(113,'medical_aid',1,'President','2026-07-26 10:34:38.144011',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(114,'medical_aid',1,'President','2026-07-26 10:34:38.853259',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(115,'medical_aid',1,'President','2026-07-26 10:36:53.598005',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(116,'medical_aid',1,'President','2026-07-26 10:36:54.940582',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(117,'medical_aid',1,'President','2026-07-26 10:37:44.124798',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(118,'medical_aid',1,'President','2026-07-26 10:37:44.658730',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(119,'medical_aid',1,'President','2026-07-26 10:39:19.897450',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(120,'medical_aid',1,'President','2026-07-26 10:39:20.898907',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(121,'medical_aid',1,'President','2026-07-26 10:39:47.816170',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(122,'medical_aid',1,'President','2026-07-26 10:39:48.586645',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(123,'medical_aid',1,'President','2026-07-26 10:40:26.160639',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(124,'medical_aid',1,'President','2026-07-26 10:40:26.944795',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(125,'medical_aid',1,'President','2026-07-26 10:41:05.736514',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(126,'medical_aid',1,'President','2026-07-26 10:41:06.413609',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(127,'medical_aid',1,'President','2026-07-26 10:43:13.827656',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(128,'medical_aid',1,'President','2026-07-26 10:43:14.335368',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(129,'medical_aid',1,'President','2026-07-26 10:43:41.627550',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(130,'medical_aid',1,'President','2026-07-26 10:43:42.231099',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(131,'medical_aid',1,'President','2026-07-26 10:44:23.736327',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(132,'medical_aid',1,'President','2026-07-26 10:44:24.386935',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(133,'medical_aid',1,'President','2026-07-26 10:45:45.770167',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(134,'medical_aid',1,'President','2026-07-26 10:45:46.415150',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(135,'medical_aid',1,'President','2026-07-26 10:47:09.977030',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(136,'medical_aid',1,'President','2026-07-26 10:47:10.335592',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(137,'medical_aid',1,'President','2026-07-26 10:47:27.909333',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(138,'medical_aid',1,'President','2026-07-26 10:47:28.243733',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(139,'medical_aid',1,'President','2026-07-26 10:49:23.781146',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(140,'medical_aid',1,'President','2026-07-26 10:49:24.278359',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(141,'medical_aid',1,'President','2026-07-26 10:49:45.849794',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(142,'medical_aid',1,'President','2026-07-26 10:49:46.453020',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(143,'medical_aid',1,'President','2026-07-26 10:50:09.140655',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(144,'medical_aid',1,'President','2026-07-26 10:50:09.321910',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(145,'medical_aid',1,'President','2026-07-26 10:50:36.994950',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(146,'medical_aid',1,'President','2026-07-26 10:50:38.020949',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(147,'medical_aid',1,'President','2026-07-26 10:50:59.772001',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(148,'medical_aid',1,'President','2026-07-26 10:51:00.063927',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(149,'medical_aid',1,'President','2026-07-26 10:51:21.438218',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(150,'medical_aid',1,'President','2026-07-26 10:51:22.054538',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(151,'medical_aid',1,'President','2026-07-26 10:53:25.398311',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(152,'medical_aid',1,'President','2026-07-26 10:53:31.790995',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(153,'medical_aid',1,'President','2026-07-26 10:54:04.181446',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(154,'medical_aid',1,'President','2026-07-26 10:54:04.726432',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(155,'medical_aid',1,'President','2026-07-26 10:55:14.397480',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(156,'medical_aid',1,'President','2026-07-26 10:55:15.464585',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(157,'medical_aid',1,'President','2026-07-26 10:57:21.919191',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
(158,'medical_aid',1,'President','2026-07-26 10:57:23.129788',23,'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36');

/*Table structure for table `supporting_proof` */

DROP TABLE IF EXISTS `supporting_proof`;

CREATE TABLE `supporting_proof` (
  `proof_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `object_id` int(10) unsigned NOT NULL CHECK (`object_id` >= 0),
  `file_path` varchar(500) NOT NULL,
  `file_name` varchar(255) NOT NULL,
  `file_type` varchar(100) NOT NULL,
  `file_sha256` varchar(64) NOT NULL,
  `row_signature` varchar(64) NOT NULL,
  `uploaded_at` datetime(6) NOT NULL,
  `content_type_id` int(11) NOT NULL,
  `uploaded_by_user_id_FK` int(11) DEFAULT NULL,
  PRIMARY KEY (`proof_id_PK`),
  KEY `SUPPORTING_PROOF_uploaded_by_user_id__a400d09d_fk_OFFICER_U` (`uploaded_by_user_id_FK`),
  KEY `SUPPORTING__content_09c351_idx` (`content_type_id`,`object_id`),
  KEY `SUPPORTING__uploade_b01f8c_idx` (`uploaded_at`),
  CONSTRAINT `SUPPORTING_PROOF_content_type_id_28f08fa8_fk_django_co` FOREIGN KEY (`content_type_id`) REFERENCES `django_content_type` (`id`),
  CONSTRAINT `SUPPORTING_PROOF_uploaded_by_user_id__a400d09d_fk_OFFICER_U` FOREIGN KEY (`uploaded_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=35 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `supporting_proof` */

insert  into `supporting_proof`(`proof_id_PK`,`object_id`,`file_path`,`file_name`,`file_type`,`file_sha256`,`row_signature`,`uploaded_at`,`content_type_id`,`uploaded_by_user_id_FK`) values 
(31,13,'supporting_proofs/2026/07/27/Screenshot_20260727-100728.jpg','Screenshot_20260727-100728.jpg','image/jpeg','fd1122d11d9dd56d8948a593d90650b3287788f101e6c6f4bdb8cac644e56895','4a069cd01f5a6d9c8842af8a0201632dc4da8361b7f73f4bac12519c09659cdf','2026-07-27 11:50:50.168687',1,NULL),
(32,13,'supporting_proofs/2026/07/27/Screenshot_20260727-100728.jpg','Screenshot_20260727-100728.jpg','image/jpeg','fd1122d11d9dd56d8948a593d90650b3287788f101e6c6f4bdb8cac644e56895','4a069cd01f5a6d9c8842af8a0201632dc4da8361b7f73f4bac12519c09659cdf','2026-07-27 11:54:00.915145',4,41),
(33,14,'supporting_proofs/2026/07/27/Screenshot_20260727-100728_wn05AcT.jpg','Screenshot_20260727-100728.jpg','image/jpeg','fd1122d11d9dd56d8948a593d90650b3287788f101e6c6f4bdb8cac644e56895','4e079b27f2af85c3d74c781c14dad8459ab69d99d36d37511dc878fbeae83eda','2026-07-27 12:02:09.785970',1,NULL),
(34,14,'supporting_proofs/2026/07/27/Screenshot_20260727-100728_wn05AcT.jpg','Screenshot_20260727-100728.jpg','image/jpeg','fd1122d11d9dd56d8948a593d90650b3287788f101e6c6f4bdb8cac644e56895','4e079b27f2af85c3d74c781c14dad8459ab69d99d36d37511dc878fbeae83eda','2026-07-27 12:03:49.277815',4,41);

/*Table structure for table `system_setting` */

DROP TABLE IF EXISTS `system_setting`;

CREATE TABLE `system_setting` (
  `setting_id_PK` int(11) NOT NULL AUTO_INCREMENT,
  `setting_key` varchar(100) NOT NULL,
  `setting_value` longtext NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `updated_by_id_FK` int(11) DEFAULT NULL,
  PRIMARY KEY (`setting_id_PK`),
  UNIQUE KEY `setting_key` (`setting_key`),
  KEY `SYSTEM_SETTING_updated_by_id_FK_d79d01db_fk_OFFICER_U` (`updated_by_id_FK`),
  CONSTRAINT `SYSTEM_SETTING_updated_by_id_FK_d79d01db_fk_OFFICER_U` FOREIGN KEY (`updated_by_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `system_setting` */

insert  into `system_setting`(`setting_id_PK`,`setting_key`,`setting_value`,`updated_at`,`updated_by_id_FK`) values 
(1,'safety_threshold','20000','2026-07-25 10:20:17.246035',NULL);

/*Table structure for table `transaction_archive` */

DROP TABLE IF EXISTS `transaction_archive`;

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
  KEY `transaction_status_abeab9_idx` (`status`),
  CONSTRAINT `transaction_archive_archived_by_user_id__95d87e41_fk_OFFICER_U` FOREIGN KEY (`archived_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`),
  CONSTRAINT `transaction_archive_member_id_FK_166fdd68_fk_MEMBER_member_id_PK` FOREIGN KEY (`member_id_FK`) REFERENCES `member` (`member_id_PK`),
  CONSTRAINT `transaction_archive_released_by_user_id__7db2dcd2_fk_OFFICER_U` FOREIGN KEY (`released_by_user_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `transaction_archive` */

/*Table structure for table `transaction_verification` */

DROP TABLE IF EXISTS `transaction_verification`;

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
  KEY `transaction_verifica_returned_by_auditor__690b24a6_fk_OFFICER_U` (`returned_by_auditor_id_FK`),
  CONSTRAINT `transaction_verifica_auditor_id_FK_36530d09_fk_OFFICER_U` FOREIGN KEY (`auditor_id_FK`) REFERENCES `officer_user` (`user_id_PK`),
  CONSTRAINT `transaction_verifica_president_id_FK_3c6de749_fk_OFFICER_U` FOREIGN KEY (`president_id_FK`) REFERENCES `officer_user` (`user_id_PK`),
  CONSTRAINT `transaction_verifica_returned_by_auditor__690b24a6_fk_OFFICER_U` FOREIGN KEY (`returned_by_auditor_id_FK`) REFERENCES `officer_user` (`user_id_PK`)
) ENGINE=InnoDB AUTO_INCREMENT=21 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

/*Data for the table `transaction_verification` */

insert  into `transaction_verification`(`verification_id`,`table_name`,`record_id`,`verification_status`,`verified_at`,`approved_at`,`auditor_id_FK`,`president_id_FK`,`auditor_remarks`,`evidence_file_hash`,`evidence_file_path`,`return_count`,`returned_by_auditor_id_FK`,`returned_reason`,`target_category`,`deposit_slip_reference`) values 
(19,'membership_fee',13,'Approved','2026-07-27 11:54:00.881819','2026-07-27 11:54:00.881819',41,41,'Auto-approved via registration final approval',NULL,NULL,0,NULL,NULL,NULL,NULL),
(20,'membership_fee',14,'Approved','2026-07-27 12:03:49.248149','2026-07-27 12:03:49.248149',41,41,'Auto-approved via registration final approval',NULL,NULL,0,NULL,NULL,NULL,NULL);

/* Procedure structure for procedure `reset_app_data` */

/*!50003 DROP PROCEDURE IF EXISTS  `reset_app_data` */;

DELIMITER $$

/*!50003 CREATE DEFINER=`root`@`localhost` PROCEDURE `reset_app_data`()
BEGIN
    DECLARE done INT DEFAULT FALSE;
    DECLARE tbl_name VARCHAR(64);

    DECLARE cur CURSOR FOR
        SELECT TABLE_NAME
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME NOT IN (
              'OFFICER_USER',
              'django_migrations',
              'django_content_type',
              'auth_permission',
              'auth_group',
              'auth_group_permissions',
              'django_admin_log',
              'django_session'
          );

    DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = TRUE;

    OPEN cur;

    read_loop: LOOP
        FETCH cur INTO tbl_name;
        IF done THEN
            LEAVE read_loop;
        END IF;

        SET @sql = CONCAT('TRUNCATE TABLE `', tbl_name, '`');
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END LOOP;

    CLOSE cur;

    DELETE FROM OFFICER_USER
    WHERE user_id_PK NOT IN (1, 2);
END */$$
DELIMITER ;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;
