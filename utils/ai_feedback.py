"""
AI Feedback Collection System
"""
import json
import os
import time
from typing import Dict, List, Optional


class AIFeedbackCollector:
    """Collects user feedback on AI responses for continuous improvement"""
    
    def __init__(self, feedback_dir: str = "data/feedback"):
        self.feedback_dir = feedback_dir
        self._ensure_feedback_dir()
        self._feedback_cache = []
        self._max_cache_size = 50
    
    def _ensure_feedback_dir(self) -> None:
        """Ensure feedback directory exists"""
        try:
            os.makedirs(self.feedback_dir, exist_ok=True)
        except Exception:
            # Fallback to current directory if we can't create the preferred one
            self.feedback_dir = "."
    
    def submit_feedback(
        self, 
        prompt: str, 
        response: str, 
        rating: int,  # 1-5 scale
        comments: Optional[str] = None,
        model: Optional[str] = None,
        context: Optional[Dict] = None
    ) -> bool:
        """Submit feedback on an AI response"""
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Prompt must be a non-empty string")
        if not isinstance(response, str):
            raise ValueError("Response must be a string")
        if not isinstance(rating, int) or rating < 1 or rating > 5:
            raise ValueError("Rating must be an integer between 1 and 5")
        
        feedback_item = {
            "timestamp": int(time.time()),
            "prompt": prompt[:500],  # Limit prompt length
            "response": response[:1000],  # Limit response length
            "rating": rating,
            "comments": comments[:500] if comments else None,
            "model": model,
            "context": context
        }
        
        self._feedback_cache.append(feedback_item)
        
        # Write to file if cache is getting large
        if len(self._feedback_cache) >= self._max_cache_size:
            self._flush_cache()
        
        return True
    
    def _flush_cache(self) -> None:
        """Write cached feedback to file"""
        if not self._feedback_cache:
            return
        
        try:
            timestamp = int(time.time())
            filename = os.path.join(self.feedback_dir, f"feedback_{timestamp}.json")
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self._feedback_cache, f, indent=2, ensure_ascii=False)
            
            self._feedback_cache = []
        except Exception:
            # If we can't write to file, keep the cache for later
            pass
    
    def flush(self) -> None:
        """Manually flush any cached feedback"""
        self._flush_cache()
    
    def get_feedback_files(self) -> List[str]:
        """Get list of feedback files"""
        try:
            files = []
            for filename in os.listdir(self.feedback_dir):
                if filename.startswith("feedback_") and filename.endswith(".json"):
                    files.append(os.path.join(self.feedback_dir, filename))
            return sorted(files, reverse=True)
        except Exception:
            return []
    
    def load_feedback(self, filename: Optional[str] = None) -> List[Dict]:
        """Load feedback from a specific file or all files"""
        if filename:
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return []
        
        # Load from all files
        all_feedback = []
        for fb_file in self.get_feedback_files():
            try:
                with open(fb_file, 'r', encoding='utf-8') as f:
                    feedback_data = json.load(f)
                    if isinstance(feedback_data, list):
                        all_feedback.extend(feedback_data)
            except Exception:
                continue
        
        return sorted(all_feedback, key=lambda x: x.get('timestamp', 0), reverse=True)
    
    def get_feedback_stats(self) -> Dict:
        """Get statistics about collected feedback"""
        all_feedback = self.load_feedback()
        
        if not all_feedback:
            return {
                'total_feedback': 0,
                'average_rating': 0,
                'rating_distribution': {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
                'feedback_with_comments': 0
            }
        
        rating_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        total_rating = 0
        comments_count = 0
        
        for feedback in all_feedback:
            rating = feedback.get('rating')
            if isinstance(rating, int) and 1 <= rating <= 5:
                rating_counts[rating] += 1
                total_rating += rating
            
            if feedback.get('comments'):
                comments_count += 1
        
        return {
            'total_feedback': len(all_feedback),
            'average_rating': round(total_rating / len(all_feedback), 2) if len(all_feedback) > 0 else 0,
            'rating_distribution': rating_counts,
            'feedback_with_comments': comments_count
        }
    
    def cleanup_old_feedback(self, max_days: int = 30) -> int:
        """Clean up old feedback files"""
        try:
            cutoff_time = time.time() - (max_days * 24 * 60 * 60)
            deleted_count = 0
            
            for filename in os.listdir(self.feedback_dir):
                if filename.startswith("feedback_") and filename.endswith(".json"):
                    filepath = os.path.join(self.feedback_dir, filename)
                    try:
                        # Extract timestamp from filename
                        timestamp_str = filename[9:-5]  # Remove "feedback_" and ".json"
                        file_time = int(timestamp_str)
                        if file_time < cutoff_time:
                            os.remove(filepath)
                            deleted_count += 1
                    except Exception:
                        continue
            
            return deleted_count
        except Exception:
            return 0