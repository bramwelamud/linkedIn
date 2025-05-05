from __future__ import annotations

import csv
import logging
import os
import random
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import pandas as pd
from dotenv import load_dotenv
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager

# Load environment variables
load_dotenv()

# Constants
MAX_APPLICATIONS_PER_SESSION = 10
MAX_SEARCH_TIME = 60 * 60  # 1 hour
MIN_DELAY = 2
MAX_DELAY = 5
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0"
]

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('linkedin_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class LinkedInEasyApplyBot:
    """Automated job application bot for LinkedIn Easy Apply positions."""
    
    def __init__(
        self,
        username: str = None,
        password: str = None,
        phone_number: str = None,
        salary: str = None,
        rate: str = None,
        uploads: Dict[str, str] = {},
        output_file: str = 'applications.csv',
        blacklist: List[str] = [],
        blacklist_titles: List[str] = [],
        experience_levels: List[int] = [],
        max_applications: int = MAX_APPLICATIONS_PER_SESSION,
        incognito: bool = False
    ) -> None:
        """
        Initialize the LinkedIn Easy Apply bot.
        
        Args:
            username: LinkedIn username/email
            password: LinkedIn password
            phone_number: Phone number for applications
            salary: Desired salary
            rate: Salary rate (per hour, year, etc.)
            uploads: Dictionary of file paths for resume, cover letter, etc.
            output_file: Path to save application results
            blacklist: List of company names to avoid
            blacklist_titles: List of job title keywords to avoid
            experience_levels: List of experience levels to target
            max_applications: Maximum number of applications per session
            incognito: Run browser in incognito mode
        """
        self.username = username or os.getenv('LINKEDIN_USERNAME')
        self.password = password or os.getenv('LINKEDIN_PASSWORD')
        self.phone_number = phone_number or os.getenv('PHONE_NUMBER')
        self.salary = salary
        self.rate = rate
        self.uploads = uploads
        self.output_file = output_file
        self.blacklist = blacklist
        self.blacklist_titles = blacklist_titles
        self.experience_levels = experience_levels
        self.max_applications = max_applications
        self.incognito = incognito
        
        # Initialize counters and trackers
        self.applied_job_ids = self._load_applied_jobs()
        self.application_count = 0
        self.qa_file = Path("qa.csv")
        self.answers = self._load_qa_data()
        
        # Initialize browser
        self.driver = self._init_browser()
        self.wait = WebDriverWait(self.driver, 30)
        
        # Locators
        self.locators = {
            "next": (By.CSS_SELECTOR, "button[aria-label='Continue to next step']"),
            "review": (By.CSS_SELECTOR, "button[aria-label='Review your application']"),
            "submit": (By.CSS_SELECTOR, "button[aria-label='Submit application']"),
            "error": (By.CLASS_NAME, "artdeco-inline-feedback__message"),
            "upload_resume": (By.XPATH, "//*[contains(@id, 'jobs-document-upload-file-input-upload-resume')]"),
            "upload_cv": (By.XPATH, "//*[contains(@id, 'jobs-document-upload-file-input-upload-cover-letter')]"),
            "follow": (By.CSS_SELECTOR, "label[for='follow-company-checkbox']"),
            "search": (By.CLASS_NAME, "jobs-search-results-list"),
           "job_cards": (By.CSS_SELECTOR, "ul.jobs-search__results-list li"),
            "fields": (By.CLASS_NAME, "jobs-easy-apply-form-section__grouping"),
            "radio_select": (By.CSS_SELECTOR, "input[type='radio']"),
            "multi_select": (By.XPATH, "//*[contains(@id, 'text-entity-list-form-component')]"),
            "text_select": (By.CLASS_NAME, "artdeco-text-input--input"),
            "easy_apply_button": (By.XPATH, '//button[contains(@class, "jobs-apply-button")]'),
            "login_username": (By.ID, 'username'),
            "login_password": (By.ID, 'password'),
            "login_button": (By.CSS_SELECTOR, 'button[type="submit"]')
        }
        
        logger.info("LinkedIn Easy Apply Bot initialized")

    def _init_browser(self) -> webdriver.Chrome:
        """Initialize and configure the Chrome browser."""
        options = Options()
        
        # Configure browser options
        if self.incognito:
            options.add_argument("--incognito")
        
        options.add_argument("--start-maximized")
        options.add_argument("--ignore-certificate-errors")
        options.add_argument('--no-sandbox')
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-blink-features")
        options.add_argument("--disable-blink-features=AutomationControlled")
        
        # Random user agent
        options.add_argument(f"user-agent={random.choice(USER_AGENTS)}")
        
        # Initialize Chrome driver
        driver = webdriver.Chrome(
            service=ChromeService(ChromeDriverManager().install()),
            options=options
        )
        
        return driver

    def _load_applied_jobs(self) -> List[str]:
        """Load previously applied job IDs from the output file."""
        try:
            df = pd.read_csv(
                self.output_file,
                header=None,
                names=['timestamp', 'job_id', 'job', 'company', 'attempted', 'result'],
                lineterminator='\n',
                encoding='utf-8'
            )
            
            df['timestamp'] = pd.to_datetime(df['timestamp'], format="%Y-%m-%d %H:%M:%S")
            df = df[df['timestamp'] > (datetime.now() - timedelta(days=2))]
            job_ids = list(df.job_id.unique())
            logger.info(f"Loaded {len(job_ids)} previously applied job IDs")
            return job_ids
        except Exception as e:
            logger.warning(f"Could not load applied jobs: {str(e)}")
            return []

    def _load_qa_data(self) -> Dict[str, str]:
        """Load question-answer pairs from CSV file."""
        if self.qa_file.is_file():
            try:
                df = pd.read_csv(self.qa_file)
                return dict(zip(df['Question'], df['Answer']))
            except Exception as e:
                logger.warning(f"Error loading QA data: {str(e)}")
                return {}
        return {}

    def _random_delay(self) -> None:
        """Add random delay between actions to simulate human behavior."""
        delay = random.uniform(MIN_DELAY, MAX_DELAY)
        logger.debug(f"Sleeping for {delay:.1f} seconds")
        time.sleep(delay)

    def login(self) -> None:
        """Log in to LinkedIn."""
        logger.info("Logging in to LinkedIn...")
        self.driver.get("https://www.linkedin.com/login")
        
        try:
            # Enter username
            username_field = self.wait.until(
                EC.presence_of_element_located(self.locators["login_username"])
            )
            username_field.send_keys(self.username)
            self._random_delay()
            
            # Enter password
            password_field = self.driver.find_element(*self.locators["login_password"])
            password_field.send_keys(self.password)
            self._random_delay()
            
            # Click login button
            login_button = self.driver.find_element(*self.locators["login_button"])
            login_button.click()
            self._random_delay()
            
            # Wait for login to complete
            time.sleep(5)
            logger.info("Login successful")
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            raise

    def search_jobs(self, position: str, location: str) -> None:
        """Search for jobs based on position and location."""
        logger.info(f"Searching for '{position}' in '{location}'")
        
        # Construct URL with experience level filters if specified
        exp_param = ""
        if self.experience_levels:
            exp_param = f"&f_E={','.join(map(str, self.experience_levels))}"
        
        search_url = (
            f"https://www.linkedin.com/jobs/search/?f_LF=f_AL&keywords="
            f"{position}&location={location}{exp_param}"
        )
        
        self.driver.get(search_url)
        self._random_delay()
        self._scroll_page()

    def _scroll_page(self) -> None:
        """Scroll the page to load all job listings."""
        try:
            scroll_results = self.wait.until(
                EC.presence_of_element_located(self.locators["search"])
            )
            
            # Gradual scroll to simulate human behavior
            for i in range(300, 3000, 100):
                self.driver.execute_script(f"arguments[0].scrollTo(0, {i})", scroll_results)
                self._random_delay()
        except TimeoutException:
            logger.warning("Search results container not found. Page may have a different structure.")
            # Fallback: scroll the entire page
            for i in range(300, 3000, 100):
                self.driver.execute_script(f"window.scrollTo(0, {i})")
                self._random_delay()

    def process_job_listings(self) -> None:
        """Process all job listings on the current page."""
        try:
            job_cards = self.wait.until(
                EC.presence_of_all_elements_located(self.locators["job_cards"])
            )
            
            job_ids = {}
            for card in job_cards:
                try:
                    # Skip if already applied or blacklisted
                    if 'Applied' in card.text:
                        continue
                        
                    if any(company in card.text for company in self.blacklist):
                        continue
                        
                    job_id = card.get_attribute("data-job-id")
                    if job_id and job_id != "search":
                        job_ids[job_id] = card.text
                except Exception as e:
                    logger.debug(f"Error processing job card: {str(e)}")
                
            logger.info(f"Found {len(job_ids)} potential jobs to apply to")
            
            # Apply to jobs
            for job_id, job_text in job_ids.items():
                if self.application_count >= self.max_applications:
                    logger.info("Reached maximum application limit for this session")
                    return
                    
                if job_id not in self.applied_job_ids:
                    success = self.apply_to_job(job_id, job_text)
                    if success:
                        self.applied_job_ids.append(job_id)
                        self.application_count += 1
                        self._random_delay()
        except TimeoutException:
            logger.warning("No job cards found on this page")

    def apply_to_job(self, job_id: str, job_text: str) -> bool:
        """Apply to a specific job posting."""
        logger.info(f"Attempting to apply to job ID: {job_id}")
        
        # Load job page
        self.driver.get(f"https://www.linkedin.com/jobs/view/{job_id}")
        self._random_delay()
        
        # Check for blacklisted titles
        job_title = self.driver.title.split(' | ')[0] if ' | ' in self.driver.title else self.driver.title
        if any(title.lower() in job_title.lower() for title in self.blacklist_titles):
            logger.info(f"Skipping blacklisted job title: {job_title}")
            self._record_application(job_id, False, "Blacklisted title")
            return False
            
        # Check for Easy Apply button
        easy_apply_button = self._get_easy_apply_button()
        if not easy_apply_button:
            logger.info("No Easy Apply button found")
            self._record_application(job_id, False, "No Easy Apply")
            return False
            
        # Click Easy Apply button
        try:
            easy_apply_button.click()
            self._random_delay()
            logger.info("Easy Apply button clicked")
        except Exception as e:
            logger.error(f"Failed to click Easy Apply: {str(e)}")
            self._record_application(job_id, False, "Easy Apply click failed")
            return False
            
        # Fill out application form
        try:
            self._fill_application_form()
            success = self._submit_application()
            
            if success:
                logger.info("Application submitted successfully")
                self._record_application(job_id, True, "Applied")
                return True
            else:
                logger.warning("Application submission failed")
                self._record_application(job_id, False, "Submission failed")
                return False
        except Exception as e:
            logger.error(f"Application error: {str(e)}")
            self._record_application(job_id, False, f"Error: {str(e)}")
            # Close any open dialogs to avoid affecting next application
            try:
                self.driver.find_element(By.CSS_SELECTOR, "button[aria-label='Dismiss']").click()
            except:
                pass
            return False

    def _get_easy_apply_button(self) -> Optional[WebElement]:
        """Find and return the Easy Apply button if present."""
        try:
            buttons = self.driver.find_elements(*self.locators["easy_apply_button"])
            for button in buttons:
                if "Easy Apply" in button.text:
                    return button
            return None
        except Exception as e:
            logger.debug(f"Easy Apply button not found: {str(e)}")
            return None

    def _fill_application_form(self) -> None:
        """Fill out the Easy Apply form fields."""
        # Fill phone number if field exists
        fields = self.driver.find_elements(*self.locators["fields"])
        for field in fields:
            if "Mobile phone number" in field.text:
                try:
                    input_field = field.find_element(By.TAG_NAME, "input")
                    input_field.clear()
                    input_field.send_keys(self.phone_number)
                    self._random_delay()
                except Exception as e:
                    logger.debug(f"Could not fill phone number: {str(e)}")
                
        # Process any questions
        self._process_questions()

    def _process_questions(self) -> None:
        """Process and answer any questions in the application form."""
        form_sections = self.driver.find_elements(*self.locators["fields"])
        
        for section in form_sections:
            try:
                question = section.text.lower()
                answer = self._get_answer(question)
                
                if not answer:
                    continue
                    
                # Try different input types
                try:
                    # Radio buttons
                    radio_buttons = section.find_elements(
                        By.CSS_SELECTOR, 
                        f"input[type='radio'][value='{answer}']"
                    )
                    if radio_buttons:
                        radio_buttons[0].click()
                        self._random_delay()
                        continue
                        
                    # Text inputs
                    text_inputs = section.find_elements(*self.locators["text_select"])
                    if text_inputs:
                        text_inputs[0].clear()
                        text_inputs[0].send_keys(answer)
                        self._random_delay()
                        continue
                        
                    # Multi-select
                    multi_selects = section.find_elements(*self.locators["multi_select"])
                    if multi_selects:
                        multi_selects[0].send_keys(answer)
                        multi_selects[0].send_keys(Keys.ENTER)
                        self._random_delay()
                        continue
                        
                except Exception as e:
                    logger.debug(f"Could not answer question '{question}': {str(e)}")
            except Exception as e:
                logger.debug(f"Error processing form section: {str(e)}")

    def _get_answer(self, question: str) -> Optional[str]:
        """Get answer for a question from stored answers or generate one."""
        # Check if we have a stored answer
        for q, a in self.answers.items():
            if q.lower() in question:
                return a
                
        # Generate answer for common questions
        if "how many years" in question or "years of experience" in question:
            return "3"
        elif "sponsor" in question or "visa" in question:
            return "No"
        elif any(x in question for x in ["do you ", "have you ", "are you ", "can you "]):
            return "Yes"
        elif "us citizen" in question or "authorized" in question or "legal right" in question:
            return "Yes"
        elif "salary" in question or "compensation" in question:
            return f"{self.salary} {self.rate}" if self.salary and self.rate else "Negotiable"
        elif any(x in question for x in ["gender", "race", "lgbtq", "ethnicity", "nationality"]):
            return "Prefer not to say"
        elif "education" in question or "degree" in question:
            return "Bachelor's degree"
        elif "when can you start" in question or "start date" in question:
            return "Immediately"
        elif "willing to relocate" in question:
            return "Yes"
            
        # If no answer found, prompt user and store for future
        logger.warning(f"No answer found for question: {question}")
        self._store_new_question(question)
        return None

    def _store_new_question(self, question: str) -> None:
        """Store a new question and its answer for future use."""
        # In a real implementation, you might want to prompt the user for an answer
        # For this example, we'll just log it
        logger.info(f"New question encountered: {question}")
        
        # Add to answers dictionary with a default response
        answer = "Yes"  # Default answer
        self.answers[question] = answer
        
        # Append to CSV
        try:
            # Create file with headers if it doesn't exist
            if not os.path.isfile(self.qa_file):
                with open(self.qa_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(["Question", "Answer"])
                    
            # Append the new question
            with open(self.qa_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([question, answer])
        except Exception as e:
            logger.error(f"Failed to save new question: {str(e)}")

    def _submit_application(self) -> bool:
        """Submit the application by navigating through all steps."""
        max_attempts = 5
        attempts = 0
        
        while attempts < max_attempts:
            attempts += 1
            self._random_delay()
            
            # Check for submit button
            submit_buttons = self.driver.find_elements(*self.locators["submit"])
            if submit_buttons:
                try:
                    submit_buttons[0].click()
                    self._random_delay()
                    return True
                except Exception as e:
                    logger.debug(f"Submit button click failed: {str(e)}")
                    continue
                    
            # Check for next/review buttons
            next_buttons = self.driver.find_elements(*self.locators["next"])
            review_buttons = self.driver.find_elements(*self.locators["review"])
            
            if next_buttons:
                try:
                    next_buttons[0].click()
                    self._random_delay()
                    continue
                except Exception as e:
                    logger.debug(f"Next button click failed: {str(e)}")
            elif review_buttons:
                try:
                    review_buttons[0].click()
                    self._random_delay()
                    continue
                except Exception as e:
                    logger.debug(f"Review button click failed: {str(e)}")
                
            # Check for file uploads
            if self._handle_file_uploads():
                continue
                
            # Check for errors
            if self._handle_errors():
                continue
                
        logger.warning("Max submission attempts reached")
        return False

    def _handle_file_uploads(self) -> bool:
        """Handle file uploads in the application form."""
        # Resume upload
        if "resume" in self.uploads and self._upload_file(
            self.locators["upload_resume"], 
            self.uploads["resume"]
        ):
            return True
            
        # Cover letter upload
        if "cover_letter" in self.uploads and self._upload_file(
            self.locators["upload_cv"], 
            self.uploads["cover_letter"]
        ):
            return True
            
        return False

    def _upload_file(self, locator: Tuple[By, str], file_path: str) -> bool:
        """Attempt to upload a file if the upload element is present."""
        try:
            upload_elements = self.driver.find_elements(*locator)
            if not upload_elements:
                return False
                
            upload_elements[0].send_keys(os.path.abspath(file_path))
            self._random_delay()
            return True
        except Exception as e:
            logger.debug(f"File upload failed: {str(e)}")
            return False

    def _handle_errors(self) -> bool:
        """Handle any errors in the application form."""
        error_messages = self.driver.find_elements(*self.locators["error"])
        if error_messages:
            logger.info(f"Errors detected in application form: {error_messages[0].text if error_messages else 'Unknown error'}")
            self._process_questions()  # Try answering questions again
            return True
        return False

    def _record_application(
        self, 
        job_id: str, 
        attempted: bool, 
        result: str
    ) -> None:
        """Record application details to the output file."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Extract job title and company from page title
        page_title = self.driver.title
        job_title = page_title.split(' | ')[0] if ' | ' in page_title else "Unknown"
        company = page_title.split(' | ')[1] if ' | ' in page_title and len(page_title.split(' | ')) > 1 else "Unknown"
        
        data = {
            'timestamp': timestamp,
            'job_id': job_id,
            'job_title': job_title,
            'company': company,
            'attempted': attempted,
            'result': result,
            'url': self.driver.current_url
        }
        
        try:
            file_exists = os.path.isfile(self.output_file)
            with open(self.output_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=data.keys())
                if not file_exists:
                    writer.writeheader()
                writer.writerow(data)
        except Exception as e:
            logger.error(f"Failed to record application: {str(e)}")

    def run(self, positions: List[str], locations: List[str]) -> None:
        """Run the bot with the given positions and locations."""
        try:
            self.login()
            
            # Process each position and location combination
            for position in positions:
                for location in locations:
                    if self.application_count >= self.max_applications:
                        break
                        
                    self.search_jobs(position, location)
                    self.process_job_listings()
                    
                    # Process multiple pages
                    for page in range(1, 4):  # Process first 3 pages
                        if self.application_count >= self.max_applications:
                            break
                            
                        self.search_jobs(position, f"{location}&start={page*25}")
                        self.process_job_listings()
            
            logger.info(f"Session complete. Applied to {self.application_count} jobs.")
        except Exception as e:
            logger.error(f"Bot encountered an error: {str(e)}")
        finally:
            self.driver.quit()


if __name__ == '__main__':
    # Load configuration
    bot_config = {
        'username': os.getenv('LINKEDIN_USERNAME'),
        'password': os.getenv('LINKEDIN_PASSWORD'),
        'phone_number': os.getenv('PHONE_NUMBER'),
        'salary': '100000',
        'rate': 'per year',
        'uploads': {
            'resume': './resume.pdf',
            'cover_letter': './cover_letter.pdf'
        },
        'blacklist': ['CompanyA', 'CompanyB'],
        'blacklist_titles': ['Senior', 'Lead'],
        'experience_levels': [2, 3],  # Associate and Mid-Senior level
        'max_applications': 10,
        'incognito': True
    }
    
    # Define search parameters separately
    positions = ['Software Engineer', 'Data Scientist']
    locations = ['United States', 'Remote']
    
    # Initialize and run bot
    bot = LinkedInEasyApplyBot(**bot_config)
    bot.run(positions, locations)
