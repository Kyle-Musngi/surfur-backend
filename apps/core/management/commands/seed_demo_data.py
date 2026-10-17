from django.core.management.base import BaseCommand
from django.utils.text import slugify
from apps.core.models import CebuLocation
from apps.accounts.models import User
from apps.shelters.models import Shelter
from apps.pets.models import Pet, PetImage
from apps.events.models import Event
from apps.donations.models import DonationCampaign
from apps.articles.models import Article, ArticleCategory
from django.utils import timezone
from datetime import timedelta
import decimal

class Command(BaseCommand):
    help = 'Seeds approved Cebu locations, sample DEMO shelters, pets, events, articles and campaigns.'

    def handle(self, *args, **options):
        self.stdout.write("Seeding Cebu locations...")
        
        cebu_data = [
            # Cities
            ("Cebu City", "city", 10.3156992, 123.8854366),
            ("Mandaue City", "city", 10.3340000, 123.9410000),
            ("Lapu-Lapu City", "city", 10.3117000, 123.9494000),
            ("Talisay City", "city", 10.2447000, 123.8494000),
            ("Naga City", "city", 10.2078000, 123.7578000),
            ("Carcar City", "city", 10.1069000, 123.6406000),
            ("Toledo City", "city", 10.3789000, 123.6417000),
            ("Bogo City", "city", 11.0500000, 124.0056000),
            ("Danao City", "city", 10.5186000, 124.0242000),
            # Municipalities (Metro Cebu & key areas)
            ("Consolacion", "municipality", 10.3800000, 123.9567000),
            ("Liloan", "municipality", 10.4000000, 123.9833000),
            ("Compostela", "municipality", 10.4561000, 124.0136000),
            ("Cordova", "municipality", 10.2528000, 123.9486000),
            ("Minglanilla", "municipality", 10.2450000, 123.7967000),
            ("San Fernando", "municipality", 10.1611000, 123.7117000),
            ("Balamban", "municipality", 10.5000000, 123.7167000),
            ("Bantayan", "municipality", 11.1667000, 123.7167000),
            ("Moalboal", "municipality", 9.9572000, 123.4019000),
            ("Oslob", "municipality", 9.5197000, 123.4300000),
            ("Argao", "municipality", 9.8833000, 123.6000000),
        ]

        locations_map = {}
        for name, loc_type, lat, lng in cebu_data:
            loc, _ = CebuLocation.objects.get_or_create(
                name=name,
                defaults={
                    'location_type': loc_type,
                    'province': 'Cebu',
                    'latitude': decimal.Decimal(str(lat)),
                    'longitude': decimal.Decimal(str(lng)),
                    'is_active': True,
                }
            )
            locations_map[name] = loc

        self.stdout.write(f"Seeded {len(locations_map)} Cebu locations.")

        # Seed Admin & Shelter Users
        admin_user, _ = User.objects.get_or_create(
            email="admin@amponcebu.ph",
            defaults={
                'full_name': "Platform Administrator",
                'role': User.Role.PLATFORM_ADMIN,
                'is_staff': True,
                'is_superuser': True,
            }
        )
        if _:
            admin_user.set_password("AdminPass123!")
            admin_user.save()

        shelter_user, _ = User.objects.get_or_create(
            email="islandrescue@amponcebu.ph",
            defaults={
                'full_name': "Island Rescue Staff",
                'role': User.Role.SHELTER_ADMIN,
                'is_staff': False,
            }
        )
        if _:
            shelter_user.set_password("ShelterPass123!")
            shelter_user.save()

        demo_adopter, _ = User.objects.get_or_create(
            email="maria.santos@example.com",
            defaults={
                'full_name': "Maria Santos",
                'role': User.Role.ADOPTER,
                'city': "Cebu City",
                'phone_number': "09171234567"
            }
        )
        if _:
            demo_adopter.set_password("AdopterPass123!")
            demo_adopter.save()

        # Seed DEMO Shelters
        self.stdout.write("Seeding sample DEMO shelters...")
        shelters_data = [
            {
                "name": "[DEMO] Island Paws Animal Rescue Cebu",
                "slug": "island-paws-rescue-cebu-demo",
                "organization_type": Shelter.OrganizationType.RESCUE_ORG,
                "description": "[DEMO DATA - Not a real shelter] Island Paws is dedicated to rescuing and rehabilitating stray dogs and cats across Metro Cebu.",
                "mission": "To eradicate animal homelessness in Cebu through rescue, rehabilitation, low-cost spay/neuter, and education.",
                "address": "Banilad, Cebu City, Cebu (Demo Location)",
                "city": locations_map["Cebu City"],
                "latitude": decimal.Decimal("10.3400000"),
                "longitude": decimal.Decimal("123.9100000"),
                "phone_number": "+63 917 000 0001",
                "email": "demo.islandpaws@amponcebu.local",
                "website": "https://amponcebu.com",
                "facebook_url": "https://facebook.com",
                "profile_image": "https://images.unsplash.com/photo-1548199973-03cce0bbc87b?w=200&h=200&fit=crop&q=80",
                "cover_image": "https://images.unsplash.com/photo-1548767797-d8c844163c4c?w=1000&h=400&fit=crop&q=80",
                "animal_types": Shelter.AnimalType.BOTH,
                "operating_hours": {"mon_fri": "9:00 AM - 4:00 PM", "sat": "10:00 AM - 2:00 PM", "sun": "Closed"},
                "adoption_requirements": "Valid Government ID, Proof of stable living condition, completed virtual/in-person home check, signature on adoption covenant.",
                "verification_status": Shelter.VerificationStatus.VERIFIED,
                "is_demo": True,
                "owner": shelter_user,
            },
            {
                "name": "[DEMO] Mandaue City Stray Care Sanctuary",
                "slug": "mandaue-stray-care-sanctuary-demo",
                "organization_type": Shelter.OrganizationType.ANIMAL_SHELTER,
                "description": "[DEMO DATA - Not a real shelter] Providing compassionate refuge and medical care to injured stray dogs and feral cats in Mandaue and Consolacion.",
                "mission": "Giving injured and abandoned street companions a safe recovery space and a second chance with a forever family.",
                "address": "Subangdaku, Mandaue City, Cebu (Demo Location)",
                "city": locations_map["Mandaue City"],
                "latitude": decimal.Decimal("10.3280000"),
                "longitude": decimal.Decimal("123.9350000"),
                "phone_number": "+63 917 000 0002",
                "email": "demo.mandauecare@amponcebu.local",
                "website": "https://amponcebu.com",
                "facebook_url": "https://facebook.com",
                "profile_image": "https://images.unsplash.com/photo-1583337130417-3346a1be7dee?w=200&h=200&fit=crop&q=80",
                "cover_image": "https://images.unsplash.com/photo-1450778869180-41d0601e046e?w=1000&h=400&fit=crop&q=80",
                "animal_types": Shelter.AnimalType.BOTH,
                "operating_hours": {"tue_sun": "10:00 AM - 5:00 PM", "mon": "Closed for sanctuary cleaning"},
                "adoption_requirements": "Interview with adoption counselor, agreement to post-adoption check-ins, fully fenced yard (for dogs).",
                "verification_status": Shelter.VerificationStatus.VERIFIED,
                "is_demo": True,
                "owner": shelter_user,
            },
            {
                "name": "[DEMO] Lapu-Lapu Coastal Felines & Hounds",
                "slug": "lapu-lapu-coastal-felines-demo",
                "organization_type": Shelter.OrganizationType.FOSTER_NETWORK,
                "description": "[DEMO DATA - Not a real shelter] A community volunteer foster network rescuing island dogs and cats across Lapu-Lapu and Cordova.",
                "mission": "Supporting volunteer fosters to rescue, nourish, and rehome island strays.",
                "address": "Maribago, Lapu-Lapu City, Cebu (Demo Location)",
                "city": locations_map["Lapu-Lapu City"],
                "latitude": decimal.Decimal("10.2880000"),
                "longitude": decimal.Decimal("123.9850000"),
                "phone_number": "+63 917 000 0003",
                "email": "demo.lapulapufelines@amponcebu.local",
                "website": "https://amponcebu.com",
                "facebook_url": "https://facebook.com",
                "profile_image": "https://images.unsplash.com/photo-1514888286974-6c03e2ca1dba?w=200&h=200&fit=crop&q=80",
                "cover_image": "https://images.unsplash.com/photo-1548802673-380ab8ebc7b7?w=1000&h=400&fit=crop&q=80",
                "animal_types": Shelter.AnimalType.CATS,
                "operating_hours": {"by_appointment": "Visits scheduled with volunteer foster parents"},
                "adoption_requirements": "Indoor-only commitment for cats, valid ID, and agreement to spay/neuter reminder schedule.",
                "verification_status": Shelter.VerificationStatus.PENDING,
                "is_demo": True,
                "owner": admin_user,
            }
        ]

        shelters_map = {}
        for s_data in shelters_data:
            s_obj, created = Shelter.objects.get_or_create(
                slug=s_data['slug'],
                defaults=s_data
            )
            shelters_map[s_obj.slug] = s_obj

        # Seed DEMO Pets
        self.stdout.write("Seeding sample DEMO pets...")
        pets_data = [
            {
                "shelter": shelters_map["island-paws-rescue-cebu-demo"],
                "name": "Barako",
                "species": Pet.Species.DOG,
                "breed": "Aspin (Asong Pinoy)",
                "sex": Pet.Sex.MALE,
                "size": Pet.Size.MEDIUM,
                "color": "Brindle / Tan",
                "age_years": 2,
                "age_months": 0,
                "age_category": Pet.AgeCategory.ADULT,
                "description": "Barako is a gentle, loyal Aspin rescued from a construction site in IT Park. He loves gentle ear scratches and walks on a leash.",
                "personality": "Calm, affectionate, loyal, food-motivated.",
                "rescue_story": "Rescued during a rainy night in Cebu IT Park with minor abrasions. He has fully recovered and is eager for a loving family.",
                "is_vaccinated": True,
                "is_dewormed": True,
                "is_sterilized": True,
                "good_with_children": True,
                "good_with_dogs": True,
                "good_with_cats": False,
                "adoption_status": Pet.AdoptionStatus.AVAILABLE,
                "is_published": True,
                "image_url": "https://images.unsplash.com/photo-1543466835-00a7907e9de1?w=600&h=500&fit=crop&q=80"
            },
            {
                "shelter": shelters_map["island-paws-rescue-cebu-demo"],
                "name": "Luna",
                "species": Pet.Species.CAT,
                "breed": "Puspin (Pusang Pinoy)",
                "sex": Pet.Sex.FEMALE,
                "size": Pet.Size.SMALL,
                "color": "Calico (White, Orange, Black)",
                "age_years": 1,
                "age_months": 2,
                "age_category": Pet.AgeCategory.YOUNG,
                "description": "Luna is a playful calico girl who adores feather toys and purrs loudly the moment you hold her.",
                "personality": "Playful, vocal, cuddly, curious.",
                "rescue_story": "Found abandoned near a bakery in Banilad when she was just two months old. Thrived in loving foster care.",
                "is_vaccinated": True,
                "is_dewormed": True,
                "is_sterilized": True,
                "good_with_children": True,
                "good_with_dogs": True,
                "good_with_cats": True,
                "adoption_status": Pet.AdoptionStatus.AVAILABLE,
                "is_published": True,
                "image_url": "https://images.unsplash.com/photo-1514888286974-6c03e2ca1dba?w=600&h=500&fit=crop&q=80"
            },
            {
                "shelter": shelters_map["mandaue-stray-care-sanctuary-demo"],
                "name": "Bantay",
                "species": Pet.Species.DOG,
                "breed": "Aspin mix",
                "sex": Pet.Sex.MALE,
                "size": Pet.Size.LARGE,
                "color": "Black & White",
                "age_years": 3,
                "age_months": 6,
                "age_category": Pet.AgeCategory.ADULT,
                "description": "Bantay is a noble companion who will loyally watch over your garden and loves lazy Sunday afternoon naps.",
                "personality": "Loyal, observant, quiet, gentle giant.",
                "rescue_story": "Found with an injured front paw along Mandaue highway. He received surgery, therapy, and now walks happily without a limp.",
                "is_vaccinated": True,
                "is_dewormed": True,
                "is_sterilized": True,
                "good_with_children": True,
                "good_with_dogs": True,
                "good_with_cats": None,
                "adoption_status": Pet.AdoptionStatus.AVAILABLE,
                "is_published": True,
                "image_url": "https://images.unsplash.com/photo-1587300003388-59208cc962cb?w=600&h=500&fit=crop&q=80"
            },
            {
                "shelter": shelters_map["mandaue-stray-care-sanctuary-demo"],
                "name": "Muning",
                "species": Pet.Species.CAT,
                "breed": "Puspin Tabby",
                "sex": Pet.Sex.FEMALE,
                "size": Pet.Size.SMALL,
                "color": "Grey Tabby",
                "age_years": 0,
                "age_months": 4,
                "age_category": Pet.AgeCategory.BABY,
                "description": "Muning is an energetic, wide-eyed kitten who loves cardboard boxes, climbing cat trees, and gentle chin scratches.",
                "personality": "Energetic, inquisitive, cuddly.",
                "rescue_story": "Rescued with her two siblings from under a parked tricycle in Subangdaku.",
                "is_vaccinated": True,
                "is_dewormed": True,
                "is_sterilized": False,
                "good_with_children": True,
                "good_with_dogs": True,
                "good_with_cats": True,
                "adoption_status": Pet.AdoptionStatus.AVAILABLE,
                "is_published": True,
                "image_url": "https://images.unsplash.com/photo-1533738363-b7f9aef128ce?w=600&h=500&fit=crop&q=80"
            },
            {
                "shelter": shelters_map["lapu-lapu-coastal-felines-demo"],
                "name": "Kape",
                "species": Pet.Species.CAT,
                "breed": "Puspin Tortoiseshell",
                "sex": Pet.Sex.FEMALE,
                "size": Pet.Size.SMALL,
                "color": "Tortoiseshell",
                "age_years": 2,
                "age_months": 0,
                "age_category": Pet.AgeCategory.ADULT,
                "description": "Kape has a quiet, charming personality with an expressive tortoiseshell coat. Ideal for quiet apartments.",
                "personality": "Independent, sweet, quiet, relaxed.",
                "rescue_story": "Surrendered by an elderly caregiver moving overseas. Litter-trained and very well-mannered.",
                "is_vaccinated": True,
                "is_dewormed": True,
                "is_sterilized": True,
                "good_with_children": True,
                "good_with_dogs": None,
                "good_with_cats": True,
                "adoption_status": Pet.AdoptionStatus.AVAILABLE,
                "is_published": True,
                "image_url": "https://images.unsplash.com/photo-1518791841217-8f162f1e1131?w=600&h=500&fit=crop&q=80"
            },
            {
                "shelter": shelters_map["island-paws-rescue-cebu-demo"],
                "name": "Tagpi",
                "species": Pet.Species.DOG,
                "breed": "Aspin",
                "sex": Pet.Sex.FEMALE,
                "size": Pet.Size.MEDIUM,
                "color": "White with Brown Patches",
                "age_years": 0,
                "age_months": 8,
                "age_category": Pet.AgeCategory.YOUNG,
                "description": "Tagpi is a cheerful puppy who knows basic commands like 'sit' and 'paw'. Loves playing fetch on grass.",
                "personality": "Friendly, fast learner, high energy, affectionate.",
                "rescue_story": "Rescued near Talisay bridge as an underweight stray pup. Healthy, energized, and ready for adventure.",
                "is_vaccinated": True,
                "is_dewormed": True,
                "is_sterilized": True,
                "good_with_children": True,
                "good_with_dogs": True,
                "good_with_cats": True,
                "adoption_status": Pet.AdoptionStatus.AVAILABLE,
                "is_published": True,
                "image_url": "https://images.unsplash.com/photo-1537151625747-768eb6cf92b2?w=600&h=500&fit=crop&q=80"
            }
        ]

        for p_data in pets_data:
            img_url = p_data.pop("image_url")
            p_obj, created = Pet.objects.get_or_create(
                name=p_data["name"],
                shelter=p_data["shelter"],
                defaults=p_data
            )
            PetImage.objects.get_or_create(
                pet=p_obj,
                image_url=img_url,
                defaults={"is_primary": True, "alt_text": f"Photo of {p_obj.name}"}
            )

        # Seed Sample Events
        self.stdout.write("Seeding sample events...")
        Event.objects.get_or_create(
            title="Cebu Paws Adoption Weekend & Pet Fair",
            host_shelter=shelters_map["island-paws-rescue-cebu-demo"],
            defaults={
                "description": "Meet friendly adoptable Aspins and Puspins in person! Featuring free vet checkups, anti-rabies vaccination, and pet care talks.",
                "event_type": Event.EventType.ADOPTION_DRIVE,
                "start_datetime": timezone.now() + timedelta(days=7),
                "end_datetime": timezone.now() + timedelta(days=7, hours=6),
                "venue_name": "Ayala Center Cebu Terraces (Outdoor Area)",
                "venue_address": "Cardinal Rosales Ave, Cebu City, Cebu",
                "city": locations_map["Cebu City"],
                "contact_info": "islandrescue@amponcebu.ph",
                "registration_required": False,
                "cover_photo": "https://images.unsplash.com/photo-1601758228041-f3b2795255f1?w=800&h=400&fit=crop&q=80",
                "status": Event.Status.UPCOMING,
                "is_published": True,
            }
        )

        # Seed Sample Educational Articles
        self.stdout.write("Seeding educational articles...")
        cat_care, _ = ArticleCategory.objects.get_or_create(name="Adoption Guide", slug="adoption-guide")
        cat_health, _ = ArticleCategory.objects.get_or_create(name="Pet Health & Care", slug="pet-health")

        Article.objects.get_or_create(
            slug="first-time-adopter-checklist-cebu",
            defaults={
                "title": "First-Time Pet Adopter Checklist: Preparing Your Home in Cebu",
                "category": cat_care,
                "author": admin_user,
                "language": Article.Language.ENGLISH,
                "status": Article.Status.PUBLISHED,
                "published_at": timezone.now(),
                "cover_image": "https://images.unsplash.com/photo-1450778869180-41d0601e046e?w=800&h=400&fit=crop&q=80",
                "excerpt": "Bringing home an Aspin or Puspin? Here is a practical, step-by-step checklist to pet-proof your home, arrange vet care, and welcome your new companion.",
                "content": """### Preparing for Your Rescued Pet in Cebu

Adopting a rescued dog or cat brings immense joy to your household. Before welcoming your new furry friend home, take these practical preparation steps:

#### 1. Secure Living Spaces & Gates
- Inspect yard fences for gaps where curious puppies or cats could squeeze through.
- For apartment dwellers, consider mesh screens on balconies and windows.

#### 2. Essential Supplies to Prepare
- Balanced food appropriate for their life stage (puppy/kitten vs adult).
- Stainless steel or ceramic food and water bowls.
- Comfortable bed or washable fleece blanket.
- Collar/harness with identification tag and sturdy walking leash.
- Litter box and unscented clumping litter (for cats).

#### 3. Establish a Vet Relationship in Cebu
Schedule an initial wellness visit with a licensed Cebu veterinarian within the first 7 to 10 days to establish medical records, confirm vaccine schedules, and set up routine parasite prevention.

*Remember: This guide offers general educational advice and does not substitute for personalized veterinary diagnosis.*"""
            }
        )

        # Seed Sample Donation Campaign
        self.stdout.write("Seeding sample donation campaign...")
        DonationCampaign.objects.get_or_create(
            title="Metro Cebu Spay & Neuter Outreach (Kapon Program)",
            shelter=shelters_map["island-paws-rescue-cebu-demo"],
            defaults={
                "description": "Helping fund 100 free and low-cost spay and neuter surgeries for community strays and low-income pet owners across Metro Cebu.",
                "purpose": "Funds directly cover surgical consumables, anesthesia, antibiotics, and post-op pain management for rescued community dogs and cats.",
                "target_amount": decimal.Decimal("50000.00"),
                "confirmed_amount": decimal.Decimal("18500.00"),
                "status": DonationCampaign.Status.ACTIVE,
                "cover_image": "https://images.unsplash.com/photo-1548767797-d8c844163c4c?w=800&h=400&fit=crop&q=80",
                "is_published": True,
            }
        )

        self.stdout.write(self.style.SUCCESS("Demo data seeded successfully for AmponCebu!"))
